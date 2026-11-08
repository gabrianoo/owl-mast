package com.aisquad.owlmast.jobs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.aisquad.owlmast.OwlMastApplication;
import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.fixtures.notes.DbProbe;
import com.aisquad.owlmast.fixtures.notes.DbProbe.WorkRow;
import com.aisquad.owlmast.fixtures.notes.EffectStore;
import com.aisquad.owlmast.fixtures.notes.FollowUpHandler;
import com.aisquad.owlmast.fixtures.notes.NotesFixture;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.AuditedMode;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.Failure;
import com.aisquad.owlmast.fixtures.notes.NotesFixtureConfiguration;
import com.aisquad.owlmast.jobs.adapter.scheduling.WorkScheduler;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.OwlMastPostgres;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * AC6 and AC9: a first application instance leaves pending work, a running item under a live lease
 * and unpublished audit intents behind when it stops; a second instance against the same database
 * finishes all of them through in-process scheduling alone. This proves process restart with
 * Testcontainers only; live pod replacement belongs to OM-18.02.
 */
class ProcessRestartRecoveryIT {

  private static final ScopeContext TENANT_A = ScopeContext.of("tenant-a", "person-a");
  private static final ScopeContext TENANT_B = ScopeContext.of("tenant-b", "person-b");
  private static final AuditActor ACTOR = AuditActor.of(ActorKind.HUMAN, "person-a");

  private static PostgreSQLContainer database;

  @BeforeAll
  static void startDatabase() {
    database = OwlMastPostgres.vectorChord();
    database.start();
  }

  @AfterAll
  static void stopDatabase() {
    if (database != null) {
      database.stop();
    }
  }

  @Test
  void aNewInstanceFinishesTheWorkAndIntentsTheStoppedInstanceLeftBehind() {
    UUID interrupted;
    try (ConfigurableApplicationContext first =
        start(
            Map.of(
                "owlmast.jobs.scheduler.enabled",
                "false",
                "owlmast.jobs.lease-duration",
                "PT2S"))) {
      assertThat(first.getBeanProvider(WorkScheduler.class).getIfAvailable()).isNull();
      NotesFixture notes = first.getBean(NotesFixture.class);
      DbProbe probe = first.getBean(DbProbe.class);
      notes.ensureTable().block();
      probe.clearAll();

      for (int i = 0; i < 3; i++) {
        notes
            .createWithFollowUp("a-" + i, Failure.NONE)
            .contextWrite(Scopes.bind(TENANT_A))
            .block();
      }
      notes.createWithFollowUp("b-0", Failure.NONE).contextWrite(Scopes.bind(TENANT_B)).block();
      notes
          .auditedCreate("a-audit-1", ACTOR, "corr-r1", AuditedMode.SUCCEED)
          .contextWrite(Scopes.bind(TENANT_A))
          .block();
      notes
          .auditedCreate("a-audit-2", ACTOR, "corr-r2", AuditedMode.SUCCEED)
          .contextWrite(Scopes.bind(TENANT_A))
          .block();
      notes
          .auditedCreate("b-audit-1", ACTOR, "corr-r3", AuditedMode.SUCCEED)
          .contextWrite(Scopes.bind(TENANT_B))
          .block();

      // The stopping instance had claimed one item and died holding a live lease.
      interrupted = probe.workItems().get(0).id();
      probe.runSql(
          "update jobs.work_item set status = 'RUNNING', attempt_count = 1,"
              + " lease_owner = 'stopped-instance', lease_token = gen_random_uuid(),"
              + " lease_expires_at = now() + interval '2 seconds', updated_at = now()"
              + " where id = '"
              + interrupted
              + "'");

      assertThat(probe.count("select count(*) from jobs.work_item where status = 'SUCCEEDED'"))
          .isZero();
      assertThat(
              probe.count(
                  "select count(*) from audit.publication_intent where published_at is null"))
          .isEqualTo(3);
      assertThat(probe.count("select count(*) from audit.event")).isZero();
    }

    try (ConfigurableApplicationContext second =
        start(
            Map.of(
                "owlmast.jobs.scheduler.enabled", "true",
                "owlmast.jobs.poll-interval", "PT0.2S",
                "owlmast.jobs.lease-duration", "PT2S"))) {
      assertThat(second.getBean(WorkScheduler.class)).isNotNull();
      DbProbe probe = second.getBean(DbProbe.class);

      await()
          .atMost(Duration.ofSeconds(30))
          .pollInterval(Duration.ofMillis(200))
          .untilAsserted(() -> {
            assertThat(
                    probe.count("select count(*) from jobs.work_item where status <> 'SUCCEEDED'"))
                .isZero();
            assertThat(
                    probe.count(
                        "select count(*) from audit.publication_intent where published_at is null"))
                .isZero();
          });

      List<WorkRow> rows = probe.workItems();
      assertThat(rows).hasSize(7);
      assertThat(probe.count("select count(*) from audit.event")).isEqualTo(3);
      WorkRow reclaimed = probe.work(interrupted);
      assertThat(reclaimed.leaseOwner()).isNotEqualTo("stopped-instance");
      assertThat(reclaimed.attempts()).as("reclaimed after the lease expired").isEqualTo(2);
      assertThat(rows)
          .filteredOn(row -> row.type().equals(FollowUpHandler.TYPE.value()))
          .allSatisfy(row -> assertThat(row.tenant()).isIn("tenant-a", "tenant-b"));
      EffectStore effects = second.getBean(EffectStore.class);
      assertThat(effects.distinctKeys()).isEqualTo(4);
      assertThat(effects.totalReceived()).isEqualTo(4);
    }
  }

  /** Settings go in as command-line arguments so they outrank application.yaml. */
  private static ConfigurableApplicationContext start(Map<String, String> settings) {
    Map<String, String> properties = new HashMap<>(settings);
    properties.put(
        "spring.r2dbc.url",
        "r2dbc:postgresql://"
            + database.getHost()
            + ":"
            + database.getFirstMappedPort()
            + "/"
            + database.getDatabaseName());
    properties.put("spring.r2dbc.username", database.getUsername());
    properties.put("spring.r2dbc.password", database.getPassword());
    properties.put("spring.flyway.url", database.getJdbcUrl());
    properties.put("spring.flyway.user", database.getUsername());
    properties.put("spring.flyway.password", database.getPassword());
    properties.put("server.port", "0");
    String[] arguments =
        properties.entrySet().stream()
            .map(entry -> "--" + entry.getKey() + "=" + entry.getValue())
            .toArray(String[]::new);
    return new SpringApplicationBuilder(
            OwlMastApplication.class,
            StubIdentityConfiguration.class,
            NotesFixtureConfiguration.class)
        .run(arguments);
  }
}
