package com.aisquad.owlmast.jobs.adapter.persistence;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.FailedWorkItem;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkStatus;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.port.ClaimedWork;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.TenantId;
import io.r2dbc.spi.Readable;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.r2dbc.core.DatabaseClient.GenericExecuteSpec;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/**
 * Jobs-owned table {@code jobs.work_item} (V002). Tenant filtering uses the setting {@link
 * ScopedTransactions#TENANT_SETTING} bound to the transaction, so a statement can only ever see the
 * bound tenant's rows; lease-fenced writes match the current token and an unexpired lease.
 */
@Repository
@RequiredArgsConstructor
class R2dbcWorkRepository implements WorkRepository {

  private static final String BOUND_TENANT =
      "current_setting('" + ScopedTransactions.TENANT_SETTING + "', true)";

  /**
   * Lease time uses {@code clock_timestamp()} (wall clock at statement execution), never {@code
   * now()}, which PostgreSQL freezes at transaction start: a handler that started under a valid
   * lease and finishes after it expired must not be able to commit (AC2).
   */
  static final String WALL_CLOCK = "clock_timestamp()";

  private static final String LEASE_IS_CURRENT =
      " where id = :id and tenant_id = "
          + BOUND_TENANT
          + " and status = 'RUNNING' and lease_token = :token and lease_expires_at > "
          + WALL_CLOCK;
  private static final String DUE =
      "((status = 'PENDING' and next_attempt_at <= "
          + WALL_CLOCK
          + ") or (status = 'RUNNING' and lease_expires_at <= "
          + WALL_CLOCK
          + "))";
  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final TypeReference<Map<String, String>> PAYLOAD = new TypeReference<>() {};

  private final DatabaseClient databaseClient;

  @Override
  public Mono<UUID> insert(
      UUID id,
      EnqueueRequest request,
      int contractVersion,
      int maxAttempts,
      PrincipalId enqueuedBy) {
    GenericExecuteSpec spec =
        databaseClient
            .sql(
                "insert into jobs.work_item (id, tenant_id, work_type, contract_version, payload,"
                    + " status, attempt_count, max_attempts, next_attempt_at, enqueued_by,"
                    + " correlation_id) values (:id, "
                    + BOUND_TENANT
                    + ", :type, :version, cast(:payload as jsonb), 'PENDING', 0, :maxAttempts,"
                    + " now(), :enqueuedBy, :correlationId)")
            .bind("id", id)
            .bind("type", request.type().value())
            .bind("version", contractVersion)
            .bind("payload", JSON.writeValueAsString(request.payload()))
            .bind("maxAttempts", maxAttempts)
            .bind("enqueuedBy", enqueuedBy.value());
    return bindOptional(spec, "correlationId", request.correlationId())
        .fetch()
        .rowsUpdated()
        .thenReturn(id);
  }

  @Override
  public Flux<ClaimedWork> claim(int limit, Duration lease, String leaseOwner) {
    return databaseClient
        .sql(
            "with due as (select id from jobs.work_item where tenant_id = "
                + BOUND_TENANT
                + " and "
                + DUE
                + " and attempt_count < max_attempts order by next_attempt_at, created_at"
                + " limit :limit for update skip locked)"
                + " update jobs.work_item w set status = 'RUNNING',"
                + " attempt_count = w.attempt_count + 1, lease_owner = :owner,"
                + " lease_token = gen_random_uuid(),"
                + " lease_expires_at = "
                + WALL_CLOCK
                + " + make_interval(secs => :leaseSeconds),"
                + " updated_at = "
                + WALL_CLOCK
                + " from due where w.id = due.id"
                + " returning w.id, w.tenant_id, w.work_type, w.contract_version,"
                + " w.payload::text as payload, w.attempt_count, w.max_attempts, w.correlation_id,"
                + " w.lease_token, w.lease_expires_at")
        .bind("limit", (long) limit)
        .bind("owner", leaseOwner)
        .bind("leaseSeconds", seconds(lease))
        .map(R2dbcWorkRepository::toClaimedWork)
        .all();
  }

  @Override
  public Mono<Long> failExhaustedExpiredLeases(String safeReason) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = 'FAILED', failure_reason = :reason,"
                + " finished_at = "
                + WALL_CLOCK
                + ", updated_at = "
                + WALL_CLOCK
                + " where tenant_id = "
                + BOUND_TENANT
                + " and status = 'RUNNING' and lease_expires_at <= "
                + WALL_CLOCK
                + " and attempt_count >= max_attempts")
        .bind("reason", safeReason)
        .fetch()
        .rowsUpdated();
  }

  @Override
  public Mono<Boolean> complete(UUID id, UUID leaseToken, EffectOutcome outcome) {
    WorkStatus status =
        outcome instanceof EffectOutcome.Applied
            ? WorkStatus.SUCCEEDED
            : WorkStatus.OUTCOME_UNCERTAIN;
    String effect = outcome instanceof EffectOutcome.Applied ? "APPLIED" : "UNCERTAIN";
    return databaseClient
        .sql(
            "update jobs.work_item set status = :status, effect_outcome = :effect,"
                + " effect_reference = :reference, finished_at = "
                + WALL_CLOCK
                + ", updated_at = "
                + WALL_CLOCK
                + LEASE_IS_CURRENT)
        .bind("status", status.name())
        .bind("effect", effect)
        .bind("reference", outcome.reference())
        .bind("id", id)
        .bind("token", leaseToken)
        .fetch()
        .rowsUpdated()
        .map(rows -> rows == 1);
  }

  @Override
  public Mono<Boolean> fail(
      UUID id, UUID leaseToken, String safeReason, Duration backoff, boolean terminal) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = :status, failure_reason = :reason,"
                + " next_attempt_at = "
                + WALL_CLOCK
                + " + make_interval(secs => :backoffSeconds),"
                + " finished_at = case when :terminal then "
                + WALL_CLOCK
                + " else null end, updated_at = "
                + WALL_CLOCK
                + LEASE_IS_CURRENT)
        .bind("status", terminal ? WorkStatus.FAILED.name() : WorkStatus.PENDING.name())
        .bind("reason", safeReason)
        .bind("backoffSeconds", seconds(backoff))
        .bind("terminal", terminal)
        .bind("id", id)
        .bind("token", leaseToken)
        .fetch()
        .rowsUpdated()
        .map(rows -> rows == 1);
  }

  @Override
  public Mono<Boolean> deny(UUID id, UUID leaseToken, String safeReason) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = 'DENIED', failure_reason = :reason,"
                + " finished_at = "
                + WALL_CLOCK
                + ", updated_at = "
                + WALL_CLOCK
                + LEASE_IS_CURRENT)
        .bind("reason", safeReason)
        .bind("id", id)
        .bind("token", leaseToken)
        .fetch()
        .rowsUpdated()
        .map(rows -> rows == 1);
  }

  @Override
  public Mono<Void> limitStatementTime(Duration timeout) {
    return databaseClient
        .sql("select set_config('statement_timeout', :millis, true)")
        .bind("millis", Long.toString(Math.max(1, timeout.toMillis())))
        .fetch()
        .rowsUpdated()
        .then();
  }

  @Override
  public Flux<TenantId> tenantsWithDueWork(int limit) {
    return databaseClient
        .sql(
            "select tenant_id from jobs.work_item where "
                + DUE
                + " group by tenant_id order by min(case when status = 'PENDING' then"
                + " next_attempt_at else lease_expires_at end), tenant_id limit :limit")
        .bind("limit", (long) limit)
        .map(row -> new TenantId(row.get("tenant_id", String.class)))
        .all();
  }

  @Override
  public Flux<FailedWorkItem> listTerminalFailures(int limit) {
    return databaseClient
        .sql(
            "select id, tenant_id, work_type, status, attempt_count, failure_reason, finished_at"
                + " from jobs.work_item where tenant_id = "
                + BOUND_TENANT
                + " and status in ('FAILED', 'DENIED', 'OUTCOME_UNCERTAIN')"
                + " order by finished_at desc, id limit :limit")
        .bind("limit", (long) limit)
        .map(row ->
            new FailedWorkItem(
                row.get("id", UUID.class),
                new TenantId(row.get("tenant_id", String.class)),
                new WorkType(row.get("work_type", String.class)),
                WorkStatus.valueOf(row.get("status", String.class)),
                row.get("attempt_count", Integer.class),
                Optional.ofNullable(row.get("failure_reason", String.class)),
                row.get("finished_at", OffsetDateTime.class)))
        .all();
  }

  private static ClaimedWork toClaimedWork(Readable row) {
    WorkItem item =
        new WorkItem(
            row.get("id", UUID.class),
            new TenantId(row.get("tenant_id", String.class)),
            new WorkType(row.get("work_type", String.class)),
            row.get("contract_version", Integer.class),
            JSON.readValue(row.get("payload", String.class), PAYLOAD),
            row.get("attempt_count", Integer.class),
            row.get("max_attempts", Integer.class),
            Optional.ofNullable(row.get("correlation_id", String.class)));
    return new ClaimedWork(
        item,
        row.get("lease_token", UUID.class),
        row.get("lease_expires_at", OffsetDateTime.class));
  }

  private static GenericExecuteSpec bindOptional(
      GenericExecuteSpec spec, String name, Optional<String> value) {
    return value.map(v -> spec.bind(name, v)).orElseGet(() -> spec.bindNull(name, String.class));
  }

  private static double seconds(Duration duration) {
    return duration.toMillis() / 1000.0;
  }
}
