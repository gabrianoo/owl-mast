package com.aisquad.owlmast.bootstrap;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.bootstrap.api.SchemaBaselineQuery;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.OwlMastPostgres;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.r2dbc.core.DatabaseClient;
import org.testcontainers.postgresql.PostgreSQLContainer;
import reactor.test.StepVerifier;

/** AC4: the real migration path ran against the pinned VectorChord image. */
@SpringBootTest
@Import({ContainersConfiguration.class, StubIdentityConfiguration.class})
class BootstrapMigrationIT {

  @Autowired private DatabaseClient databaseClient;
  @Autowired private SchemaBaselineQuery schemaBaselineQuery;
  @Autowired private PostgreSQLContainer database;

  @Test
  void flywayAppliedTheBootstrapMigration() {
    List<Map<String, Object>> history =
        databaseClient
            .sql(
                "select version, description, success from flyway_schema_history"
                    + " order by installed_rank")
            .fetch()
            .all()
            .collectList()
            .block();

    assertThat(history)
        .extracting(
            row -> row.get("version") + " " + row.get("description") + " " + row.get("success"))
        .containsExactly(
            "001 bootstrap infrastructure true",
            "002 jobs infrastructure true",
            "003 audit infrastructure true",
            "004 jobs tenant id not blank true",
            "005 audit tenant id not blank true");
  }

  /**
   * E01-R-02 (retro B3, R12): the suite runs migrations and the runtime as the restricted owner
   * role an installation uses, never as the container's superuser.
   */
  @Test
  void migrationsAndTheRuntimeRunAsARoleWithoutPrivilegedAttributes() {
    Map<String, Object> role =
        databaseClient
            .sql(
                "select current_user as name, rolsuper, rolcreatedb, rolcreaterole, rolreplication,"
                    + " rolbypassrls from pg_roles where rolname = current_user")
            .fetch()
            .one()
            .block();
    List<String> migratedBy =
        databaseClient
            .sql("select distinct installed_by from flyway_schema_history")
            .map(row -> row.get("installed_by", String.class))
            .all()
            .collectList()
            .block();
    List<String> tableOwners =
        databaseClient
            .sql(
                "select distinct tableowner from pg_tables"
                    + " where schemaname in ('bootstrap', 'jobs', 'audit')")
            .map(row -> row.get("tableowner", String.class))
            .all()
            .collectList()
            .block();

    assertThat(role)
        .containsEntry("name", OwlMastPostgres.APPLICATION_ROLE)
        .containsEntry("rolsuper", false)
        .containsEntry("rolcreatedb", false)
        .containsEntry("rolcreaterole", false)
        .containsEntry("rolreplication", false)
        .containsEntry("rolbypassrls", false);
    assertThat(migratedBy).containsExactly(OwlMastPostgres.APPLICATION_ROLE);
    assertThat(tableOwners).containsExactly(OwlMastPostgres.APPLICATION_ROLE);
  }

  @Test
  void vectorChordAndItsPgvectorDependencyAreInstalledAndPreloaded() throws Exception {
    List<Map<String, Object>> extensions =
        databaseClient
            .sql(
                "select extname, extversion from pg_extension"
                    + " where extname in ('vchord', 'vector') order by extname")
            .fetch()
            .all()
            .collectList()
            .block();
    // Only a superuser may read this setting, and the application role is none (E01-R-02): it is
    // read as the provisioning identity, inside the container.
    String preloaded =
        database
            .execInContainer(
                "psql",
                "--username",
                OwlMastPostgres.PROVISIONER,
                "--dbname",
                database.getDatabaseName(),
                "-Atc",
                "show shared_preload_libraries")
            .getStdout();

    assertThat(extensions)
        .extracting(row -> row.get("extname") + "=" + row.get("extversion"))
        .containsExactly("vchord=1.1.1", "vector=0.8.2");
    assertThat(preloaded).contains("vchord");
  }

  @Test
  void schemaBaselineRecordsTheExtensionVersionsThroughTheFeatureApi() {
    StepVerifier.create(schemaBaselineQuery.current())
        .assertNext(baseline -> {
          assertThat(baseline.vchordVersion()).isEqualTo("1.1.1");
          assertThat(baseline.vectorVersion()).isEqualTo("0.8.2");
          assertThat(baseline.appliedAt()).isNotNull();
          // Read from the answering server (E01-R-06); the pinned image is PostgreSQL 18.
          assertThat(baseline.postgresqlMajor()).isEqualTo(18);
          assertThat(baseline.serverIsSupported()).isTrue();
        })
        .verifyComplete();
  }

  /**
   * Extension-owned relations (pg_depend deptype e) belong to VectorChord, not to the bootstrap.
   * Besides the bootstrap baseline only the jobs- and audit-owned infrastructure tables of OM-01.03
   * exist; feature schemas arrive with their owning stories (AD-2).
   */
  @Test
  void onlyStoryOwnedInfrastructureObjectsExist() {
    List<String> tables =
        databaseClient
            .sql(
                "select n.nspname || '.' || c.relname as name from pg_class c"
                    + " join pg_namespace n on n.oid = c.relnamespace"
                    + " where c.relkind in ('r', 'p')"
                    + " and n.nspname not in ('pg_catalog', 'information_schema')"
                    + " and not exists (select 1 from pg_depend d"
                    + "   where d.objid = c.oid and d.deptype = 'e')"
                    + " order by 1")
            .map(row -> row.get("name", String.class))
            .all()
            .collectList()
            .block();

    assertThat(tables)
        .containsExactly(
            "audit.event",
            "audit.publication_intent",
            "bootstrap.schema_baseline",
            "jobs.work_item",
            "public.flyway_schema_history");
  }
}
