package com.aisquad.owlmast.jobs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.testing.OwlMastPostgres;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.LinkedHashMap;
import java.util.Map;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * E01-R-04: V004 and V005 on a database that already holds a row with a blank tenant id, the case
 * they were written for. The migrations must not fail (a failed migration stops the application
 * from starting); the check that a stored row breaks stays NOT VALID and still rejects new rows,
 * the others are validated, and the operator's VALIDATE CONSTRAINT works once the row is corrected.
 * Runs the real migrations with Flyway as the application role, in a container of its own.
 */
class TenantIdConstraintMigrationIT {

  private static final String BLANK_WORK_ITEM =
      "insert into jobs.work_item (id, tenant_id, work_type, contract_version, status,"
          + " max_attempts, next_attempt_at, enqueued_by) values (gen_random_uuid(), '   ',"
          + " 'fixture.follow-up', 1, 'PENDING', 3, now(), 'person-a')";
  private static final String BLANK_AUDIT_EVENT =
      "insert into audit.event (event_id, envelope_version, tenant_id, actor_kind, object_type,"
          + " action, outcome, occurred_at, recorded_at, correlation_id) values"
          + " (gen_random_uuid(), 1, '', 'SERVICE', 'note', 'create', 'FAILED', now(), now(),"
          + " 'c-1')";

  @Test
  void theMigrationsSurviveStoredBlankRowsAndStillRejectNewOnes() throws SQLException {
    try (PostgreSQLContainer database = OwlMastPostgres.vectorChord()) {
      database.start();
      flyway(database, "3").migrate();
      try (Connection connection = database.createConnection("");
          Statement statement = connection.createStatement()) {
        statement.execute(BLANK_WORK_ITEM);
        statement.execute(BLANK_AUDIT_EVENT);
      }

      assertThat(flyway(database, "latest").migrate().success).isTrue();

      try (Connection connection = database.createConnection("");
          Statement statement = connection.createStatement()) {
        assertThat(validated(statement))
            .as("only the table without a blank row is validated")
            .containsExactly(
                Map.entry("event_tenant_id_not_blank", false),
                Map.entry("publication_intent_tenant_id_not_blank", true),
                Map.entry("work_item_tenant_id_not_blank", false));

        assertThatThrownBy(() -> statement.execute(BLANK_WORK_ITEM))
            .as("a constraint left NOT VALID still rejects new rows")
            .hasMessageContaining("work_item_tenant_id_not_blank");
        assertThatThrownBy(() -> statement.execute(BLANK_AUDIT_EVENT))
            .hasMessageContaining("event_tenant_id_not_blank");
        assertThatThrownBy(() ->
                statement.execute(
                    "alter table jobs.work_item validate constraint"
                        + " work_item_tenant_id_not_blank"))
            .as("validation fails while the stored row is still blank")
            .hasMessageContaining("work_item_tenant_id_not_blank");

        // What the migration comment tells the operator to do: correct the rows, then validate.
        statement.execute("delete from jobs.work_item where tenant_id ~ '^[[:space:]]*$'");
        statement.execute("delete from audit.event where tenant_id ~ '^[[:space:]]*$'");
        statement.execute(
            "alter table jobs.work_item validate constraint work_item_tenant_id_not_blank");
        statement.execute("alter table audit.event validate constraint event_tenant_id_not_blank");

        assertThat(validated(statement).values()).containsOnly(true);
      }
    }
  }

  private static Flyway flyway(PostgreSQLContainer database, String target) {
    return Flyway.configure()
        .dataSource(database.getJdbcUrl(), database.getUsername(), database.getPassword())
        .locations("classpath:db/migration")
        .target(target)
        .load();
  }

  private static Map<String, Boolean> validated(Statement statement) throws SQLException {
    Map<String, Boolean> byName = new LinkedHashMap<>();
    try (ResultSet rows =
        statement.executeQuery(
            "select conname, convalidated from pg_constraint"
                + " where conname like '%tenant_id_not_blank' order by conname")) {
      while (rows.next()) {
        byName.put(rows.getString("conname"), rows.getBoolean("convalidated"));
      }
    }
    return byName;
  }
}
