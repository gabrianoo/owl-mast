package com.aisquad.owlmast.fixtures.notes;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

/**
 * Direct, test-only reads and state injections against the jobs and audit tables. Production code
 * never reads another module's tables; the tests that prove the modules may.
 */
public final class DbProbe {

  /** One {@code jobs.work_item} row. */
  public record WorkRow(
      UUID id,
      String tenant,
      String type,
      String status,
      int attempts,
      int maxAttempts,
      String reason,
      String leaseOwner,
      UUID leaseToken,
      OffsetDateTime leaseExpiresAt,
      OffsetDateTime nextAttemptAt,
      OffsetDateTime updatedAt,
      OffsetDateTime finishedAt,
      String effectOutcome,
      String effectReference,
      String enqueuedBy,
      String correlationId,
      String payload) {}

  /** One {@code audit.event} or {@code audit.publication_intent} row. */
  public record AuditRow(
      UUID eventId,
      String tenant,
      String outcome,
      String reason,
      String objectType,
      String objectId,
      String objectVersion,
      String actorKind,
      String actorId,
      String projectId,
      String correlationId,
      OffsetDateTime publishedAt) {}

  private static final String WORK_COLUMNS =
      "id, tenant_id, work_type, status, attempt_count, max_attempts, failure_reason,"
          + " lease_owner, lease_token, lease_expires_at, next_attempt_at, updated_at, finished_at,"
          + " effect_outcome, effect_reference, enqueued_by, correlation_id, payload::text as payload";
  private static final String AUDIT_COLUMNS =
      "event_id, tenant_id, outcome, reason, object_type, object_id, object_version, actor_kind,"
          + " actor_id, project_id, correlation_id, published_at";

  private final DatabaseClient databaseClient;

  public DbProbe(DatabaseClient databaseClient) {
    this.databaseClient = databaseClient;
  }

  public WorkRow work(UUID id) {
    return databaseClient
        .sql("select " + WORK_COLUMNS + " from jobs.work_item where id = :id")
        .bind("id", id)
        .map(DbProbe::toWorkRow)
        .one()
        .block();
  }

  public List<WorkRow> workItems() {
    return databaseClient
        .sql("select " + WORK_COLUMNS + " from jobs.work_item order by created_at, id")
        .map(DbProbe::toWorkRow)
        .all()
        .collectList()
        .block();
  }

  public List<AuditRow> auditEvents() {
    return databaseClient
        .sql("select " + AUDIT_COLUMNS + " from audit.event order by recorded_at, event_id")
        .map(DbProbe::toAuditRow)
        .all()
        .collectList()
        .block();
  }

  public List<AuditRow> intents() {
    return databaseClient
        .sql(
            "select "
                + AUDIT_COLUMNS
                + " from audit.publication_intent order by recorded_at, event_id")
        .map(DbProbe::toAuditRow)
        .all()
        .collectList()
        .block();
  }

  /** Every row of the table as JSON text, for secret searches across all columns. */
  public List<String> rowsAsText(String table) {
    return databaseClient
        .sql("select row_to_json(t)::text as row from " + table + " t")
        .map(row -> row.get("row", String.class))
        .all()
        .collectList()
        .block();
  }

  public long count(String countSql) {
    return databaseClient.sql(countSql).map(row -> row.get(0, Long.class)).one().block();
  }

  public List<String> columnsOf(String schema, String table) {
    return databaseClient
        .sql(
            "select column_name from information_schema.columns where table_schema = :schema"
                + " and table_name = :table order by ordinal_position")
        .bind("schema", schema)
        .bind("table", table)
        .map(row -> row.get("column_name", String.class))
        .all()
        .collectList()
        .block();
  }

  /** The definition PostgreSQL holds for a table's constraint, as {@code pg_get_constraintdef}. */
  public String constraintDefinition(String table, String constraint) {
    return databaseClient
        .sql(
            "select pg_get_constraintdef(oid) as def from pg_constraint"
                + " where conrelid = cast(:table as regclass) and conname = :constraint")
        .bind("table", table)
        .bind("constraint", constraint)
        .map(row -> row.get("def", String.class))
        .one()
        .block();
  }

  public void runSql(String sql) {
    databaseClient.sql(sql).then().block();
  }

  /** Autocommit update on its own connection, usable inside a reactive handler. */
  public Mono<Void> expireLeaseAsync(UUID id) {
    return databaseClient
        .sql(
            "update jobs.work_item set lease_expires_at = now() - interval '1 second' where id = :id")
        .bind("id", id)
        .then()
        .contextWrite(ctx -> Context.empty());
  }

  public void clearAll() {
    runSql("delete from jobs.work_item");
    runSql("delete from audit.event");
    runSql("delete from audit.publication_intent");
    runSql("delete from " + NotesFixture.TABLE);
  }

  /** Fault injection for AC4: every insert into the history raises until removed. */
  public void installAuditEventFault() {
    runSql(
        "create or replace function fixture_audit_fault() returns trigger language plpgsql as $$"
            + " begin raise exception 'fixture: injected fault before audit publication'; end $$");
    runSql(
        "create trigger fixture_audit_fault before insert on audit.event"
            + " for each row execute function fixture_audit_fault()");
  }

  public void removeAuditEventFault() {
    runSql("drop trigger if exists fixture_audit_fault on audit.event");
    runSql("drop function if exists fixture_audit_fault()");
  }

  /**
   * Makes the commit of every claim take {@code delay}: a deferred constraint trigger sleeps at
   * commit time, as a commit does that waits for a synchronous standby. The claim stays invisible
   * to other sessions meanwhile.
   */
  public void installSlowClaimCommit(Duration delay) {
    runSql(
        "create or replace function fixture_slow_claim_commit() returns trigger language plpgsql"
            + " as $$ begin perform pg_sleep("
            + delay.toMillis() / 1000.0
            + "); return null; end $$");
    runSql(
        "create constraint trigger fixture_slow_claim_commit after update on jobs.work_item"
            + " deferrable initially deferred for each row"
            + " when (old.status = 'PENDING' and new.status = 'RUNNING')"
            + " execute function fixture_slow_claim_commit()");
  }

  public void removeSlowClaimCommit() {
    runSql("drop trigger if exists fixture_slow_claim_commit on jobs.work_item");
    runSql("drop function if exists fixture_slow_claim_commit()");
  }

  /** Other sessions whose COMMIT is running right now. */
  public long commitsInFlight() {
    return count(
        "select count(*) from pg_stat_activity where state = 'active'"
            + " and pid <> pg_backend_pid() and query ilike 'commit%'");
  }

  private static WorkRow toWorkRow(io.r2dbc.spi.Readable row) {
    return new WorkRow(
        row.get("id", UUID.class),
        row.get("tenant_id", String.class),
        row.get("work_type", String.class),
        row.get("status", String.class),
        row.get("attempt_count", Integer.class),
        row.get("max_attempts", Integer.class),
        row.get("failure_reason", String.class),
        row.get("lease_owner", String.class),
        row.get("lease_token", UUID.class),
        row.get("lease_expires_at", OffsetDateTime.class),
        row.get("next_attempt_at", OffsetDateTime.class),
        row.get("updated_at", OffsetDateTime.class),
        row.get("finished_at", OffsetDateTime.class),
        row.get("effect_outcome", String.class),
        row.get("effect_reference", String.class),
        row.get("enqueued_by", String.class),
        row.get("correlation_id", String.class),
        row.get("payload", String.class));
  }

  private static AuditRow toAuditRow(io.r2dbc.spi.Readable row) {
    return new AuditRow(
        row.get("event_id", UUID.class),
        row.get("tenant_id", String.class),
        row.get("outcome", String.class),
        row.get("reason", String.class),
        row.get("object_type", String.class),
        row.get("object_id", String.class),
        row.get("object_version", String.class),
        row.get("actor_kind", String.class),
        row.get("actor_id", String.class),
        row.get("project_id", String.class),
        row.get("correlation_id", String.class),
        row.get("published_at", OffsetDateTime.class));
  }
}
