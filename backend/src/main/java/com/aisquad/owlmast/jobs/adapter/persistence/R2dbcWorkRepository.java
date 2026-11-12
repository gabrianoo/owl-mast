package com.aisquad.owlmast.jobs.adapter.persistence;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.FailedWorkItem;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.api.WorkStatus;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.port.Claim;
import com.aisquad.owlmast.jobs.port.ClaimedWork;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.TenantId;
import io.r2dbc.spi.Readable;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.r2dbc.core.DatabaseClient.GenericExecuteSpec;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/**
 * Jobs-owned table {@code jobs.work_item} (V002). Tenant filtering uses the setting {@link
 * ScopedTransactions#TENANT_SETTING} bound to the transaction, so a statement can only ever see the
 * bound tenant's rows; lease-fenced writes match the current token and an unexpired lease, and
 * every write that leaves {@code RUNNING} clears the token (the database checks that invariant).
 * {@code lease_owner} and {@code lease_expires_at} stay as a record of the last lease.
 */
@Slf4j
@Repository
@RequiredArgsConstructor
class R2dbcWorkRepository implements WorkRepository {

  /** Reason persisted for a claimed row that cannot be decoded into a {@link WorkItem}. */
  static final String REASON_UNDECODABLE = "undecodable-work-item";

  private static final String BOUND_TENANT =
      "current_setting('" + ScopedTransactions.TENANT_SETTING + "', true)";

  /**
   * Lease time uses {@code clock_timestamp()} (wall clock at statement execution), never {@code
   * now()}, which PostgreSQL freezes at transaction start: a handler that started under a valid
   * lease and finishes after it expired must not be able to commit (AC2).
   */
  static final String WALL_CLOCK = "clock_timestamp()";

  /**
   * Transaction-level advisory lock on the lease token. The claim takes it with the row and holds
   * it until its transaction has ended (PostgreSQL releases locks only after a commit is visible);
   * the give-back takes it first, so the two are serialised per token.
   */
  private static final String TOKEN_LOCK =
      "pg_advisory_xact_lock(hashtextextended(cast(:token as text), 0))";

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

  /** Work this instance can run: a registered type, written with a version this build reads. */
  private static final String CLAIMABLE =
      " and work_type = any(:types) and contract_version <= :version";

  /** Past this many doublings every backoff is at its cap; keeps the SQL arithmetic bounded. */
  private static final int MAX_BACKOFF_DOUBLINGS = 30;

  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final TypeReference<Map<String, String>> PAYLOAD = new TypeReference<>() {};

  private final DatabaseClient databaseClient;

  /** Only for the cross-tenant discovery, which has no scope to open a scoped transaction with. */
  private final TransactionalOperator transactionalOperator;

  /** The claimed columns before decoding, so a decoding failure can still name the row. */
  private record RawClaim(
      UUID id,
      String tenant,
      String type,
      int contractVersion,
      String payload,
      int attempt,
      int maxAttempts,
      String correlationId,
      UUID leaseToken,
      OffsetDateTime leaseExpiresAt) {}

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
  public Flux<Claim> claim(
      int limit, Duration lease, String leaseOwner, UUID leaseToken, Set<WorkType> types) {
    return databaseClient
        .sql(
            "with due as (select id from jobs.work_item where tenant_id = "
                + BOUND_TENANT
                + " and "
                + DUE
                + CLAIMABLE
                + " and attempt_count < max_attempts order by next_attempt_at, created_at"
                + " limit :limit for update skip locked),"
                // Held until this transaction has ended, so a give-back by the same token waits
                // for a commit that is still in flight instead of finding no row yet.
                + " held as materialized (select "
                + TOKEN_LOCK
                + ")"
                + " update jobs.work_item w set status = 'RUNNING',"
                + " attempt_count = w.attempt_count + 1, lease_owner = :owner,"
                + " lease_token = :token,"
                + " release_count = case when w.status = 'RUNNING' then 0 else w.release_count end,"
                + " lease_expires_at = "
                + WALL_CLOCK
                + " + make_interval(secs => :leaseSeconds),"
                + " updated_at = "
                + WALL_CLOCK
                + " from due, held where w.id = due.id"
                + " returning w.id, w.tenant_id, w.work_type, w.contract_version,"
                + " w.payload::text as payload, w.attempt_count, w.max_attempts, w.correlation_id,"
                + " w.lease_token, w.lease_expires_at")
        .bind("limit", (long) limit)
        .bind("owner", leaseOwner)
        .bind("token", leaseToken)
        .bind("leaseSeconds", seconds(lease))
        .bind("types", typeValues(types))
        .bind("version", WorkItemContract.VERSION)
        .map(R2dbcWorkRepository::toRawClaim)
        .all()
        .concatMap(this::decodeOrFail);
  }

  @Override
  public Mono<Long> failExhaustedExpiredLeases(String safeReason) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = 'FAILED', failure_reason = :reason,"
                + " lease_token = null, finished_at = "
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
                + " effect_reference = :reference, failure_reason = null, lease_token = null,"
                + " release_count = 0,"
                + " finished_at = "
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
                + " lease_token = null, release_count = 0, next_attempt_at = "
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
  public Mono<Integer> release(
      UUID id, UUID leaseToken, String safeReason, Duration backoffBase, Duration backoffCap) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = 'PENDING', failure_reason = :reason,"
                + " attempt_count = attempt_count - 1, lease_token = null,"
                + " release_count = release_count + 1, next_attempt_at = "
                + WALL_CLOCK
                + " + make_interval(secs => least(:baseSeconds * power(2::double precision,"
                + " least(release_count, "
                + MAX_BACKOFF_DOUBLINGS
                + ")), :capSeconds)), updated_at = "
                + WALL_CLOCK
                + LEASE_IS_CURRENT
                + " returning release_count")
        .bind("reason", safeReason)
        .bind("baseSeconds", seconds(backoffBase))
        .bind("capSeconds", seconds(backoffCap))
        .bind("id", id)
        .bind("token", leaseToken)
        .map(row -> row.get("release_count", Integer.class))
        .one();
  }

  @Override
  public Mono<Long> giveBack(UUID leaseToken, String safeReason) {
    // A statement of its own: the update below must take its snapshot after the claim that holds
    // this lock has ended, or it would still see the row as it was before the claim.
    Mono<Void> claimEnded =
        databaseClient.sql("select " + TOKEN_LOCK).bind("token", leaseToken).then();
    return claimEnded.then(giveBackNow(leaseToken, safeReason));
  }

  private Mono<Long> giveBackNow(UUID leaseToken, String safeReason) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = 'PENDING', failure_reason = :reason,"
                + " attempt_count = attempt_count - 1, lease_token = null, next_attempt_at = "
                + WALL_CLOCK
                + ", updated_at = "
                + WALL_CLOCK
                + " where tenant_id = "
                + BOUND_TENANT
                + " and status = 'RUNNING' and lease_token = :token and lease_expires_at > "
                + WALL_CLOCK)
        .bind("reason", safeReason)
        .bind("token", leaseToken)
        .fetch()
        .rowsUpdated();
  }

  @Override
  public Mono<Boolean> deny(UUID id, UUID leaseToken, String safeReason) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = 'DENIED', failure_reason = :reason,"
                + " lease_token = null, finished_at = "
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
  public Flux<TenantId> tenantsWithDueWork(
      int limit, Set<WorkType> types, Duration statementLimit) {
    return transactionalOperator.execute(
        transaction -> limitStatementTime(statementLimit).thenMany(dueTenants(limit, types)));
  }

  private Flux<TenantId> dueTenants(int limit, Set<WorkType> types) {
    return databaseClient
        .sql(
            "select tenant_id from jobs.work_item where "
                + DUE
                + CLAIMABLE
                + " group by tenant_id order by min(case when status = 'PENDING' then"
                + " next_attempt_at else lease_expires_at end), tenant_id limit :limit")
        .bind("limit", (long) limit)
        .bind("types", typeValues(types))
        .bind("version", WorkItemContract.VERSION)
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

  /**
   * Decodes a claimed row; a row that cannot become a {@link WorkItem} (a payload that is not a map
   * of strings, a bound that was tightened, a hand-edited row) is marked terminal {@code FAILED}
   * under the lease this claim took and reported as {@link Claim.Undecodable}, so the queue moves
   * past it within the same batch.
   */
  private Mono<Claim> decodeOrFail(RawClaim raw) {
    return Mono.<Claim>fromCallable(() -> decode(raw))
        .onErrorResume(undecodable -> {
          log.warn(
              "Work item {} ({}) cannot be decoded and is failed terminally: {}",
              raw.id(),
              raw.type(),
              SafeFailure.describe(undecodable));
          return failUndecodable(raw).thenReturn(new Claim.Undecodable(raw.id()));
        });
  }

  private static ClaimedWork decode(RawClaim raw) {
    WorkItem item =
        new WorkItem(
            raw.id(),
            new TenantId(raw.tenant()),
            new WorkType(raw.type()),
            raw.contractVersion(),
            JSON.readValue(raw.payload(), PAYLOAD),
            raw.attempt(),
            raw.maxAttempts(),
            Optional.ofNullable(raw.correlationId()));
    return new ClaimedWork(item, raw.leaseToken(), raw.leaseExpiresAt());
  }

  private Mono<Void> failUndecodable(RawClaim raw) {
    return databaseClient
        .sql(
            "update jobs.work_item set status = 'FAILED', failure_reason = :reason,"
                + " lease_token = null, finished_at = "
                + WALL_CLOCK
                + ", updated_at = "
                + WALL_CLOCK
                + LEASE_IS_CURRENT)
        .bind("reason", REASON_UNDECODABLE)
        .bind("id", raw.id())
        .bind("token", raw.leaseToken())
        .fetch()
        .rowsUpdated()
        .then();
  }

  private static RawClaim toRawClaim(Readable row) {
    return new RawClaim(
        row.get("id", UUID.class),
        row.get("tenant_id", String.class),
        row.get("work_type", String.class),
        row.get("contract_version", Integer.class),
        row.get("payload", String.class),
        row.get("attempt_count", Integer.class),
        row.get("max_attempts", Integer.class),
        row.get("correlation_id", String.class),
        row.get("lease_token", UUID.class),
        row.get("lease_expires_at", OffsetDateTime.class));
  }

  private static String[] typeValues(Set<WorkType> types) {
    return types.stream().map(WorkType::value).sorted().toArray(String[]::new);
  }

  private static GenericExecuteSpec bindOptional(
      GenericExecuteSpec spec, String name, Optional<String> value) {
    return value.map(v -> spec.bind(name, v)).orElseGet(() -> spec.bindNull(name, String.class));
  }

  private static double seconds(Duration duration) {
    return duration.toMillis() / 1000.0;
  }
}
