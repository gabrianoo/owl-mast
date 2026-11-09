package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.DispatchAuthorization;
import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.NonRetryableWorkException;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.ClaimedWork;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.platform.scope.ServiceIdentity;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.Duration;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.TimeoutException;
import lombok.extern.slf4j.Slf4j;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * One wake-up of the durable-work processor (AD-6). Tenants with due work are discovered by
 * identifier only; each tenant's items are then claimed, authorized, run and completed inside
 * scoped transactions bound to that tenant under the backend service identity (AD-3, AC8).
 *
 * <ul>
 *   <li>Claiming is bounded and lease-based and takes only work this instance can run (registered
 *       types, a supported contract version); expired leases are reclaimed by the next claim.
 *   <li>The authorization recheck runs before every dispatch; DENY is terminal, UNDECIDED and
 *       errors (a recheck that does not answer within the deadline included) release the item for a
 *       later attempt without counting one (AC7).
 *   <li>The handler and the completion write share one transaction fenced by the lease token: a
 *       stale lease rolls back the handler's database effects and the write changes nothing (AC2).
 *   <li>{@link RetryPolicy#handlerDeadline()} is measured from the claim. A handler still running
 *       at the deadline is cancelled and the attempt fails with {@value #REASON_DEADLINE_EXCEEDED};
 *       its statements are bounded on the server by {@link RetryPolicy#statementTimeout()}, so one
 *       hung handler, including one blocked inside the database, cannot stall the dispatch of every
 *       other item and tenant.
 *   <li>Failed attempts persist the attempt count, a capped backoff and the exception class chain
 *       only; the last permitted attempt, or a {@link NonRetryableWorkException}, makes the item
 *       terminal (AC5).
 * </ul>
 */
@Slf4j
public final class WorkProcessor {

  static final String REASON_UNREGISTERED = "unregistered-work-type";
  static final String REASON_AUTHORIZATION_DENIED = "authorization-denied";
  static final String REASON_AUTHORIZATION_UNDECIDED = "authorization-undecided";
  static final String REASON_LEASE_EXHAUSTED = "lease-expired-attempts-exhausted";
  static final String REASON_NO_EFFECT_OUTCOME = "handler-returned-no-effect-outcome";
  static final String REASON_DEADLINE_EXCEEDED = "handler-deadline-exceeded";
  static final int MAX_TENANTS_PER_WAKE = 100;

  private final ScopedTransactions transactions;
  private final WorkRepository repository;
  private final HandlerRegistry registry;
  private final DispatchAuthorization authorization;
  private final RetryPolicy policy;
  private final String leaseOwner;

  public WorkProcessor(
      ScopedTransactions transactions,
      WorkRepository repository,
      HandlerRegistry registry,
      DispatchAuthorization authorization,
      RetryPolicy policy,
      String leaseOwner) {
    this.transactions = Objects.requireNonNull(transactions, "transactions");
    this.repository = Objects.requireNonNull(repository, "repository");
    this.registry = Objects.requireNonNull(registry, "registry");
    this.authorization = Objects.requireNonNull(authorization, "authorization");
    this.policy = Objects.requireNonNull(policy, "policy");
    this.leaseOwner = Objects.requireNonNull(leaseOwner, "leaseOwner");
  }

  public String leaseOwner() {
    return leaseOwner;
  }

  /** Processes every tenant with due work once; returns the number of items dispatched. */
  public Mono<Long> runOnce() {
    return repository
        .tenantsWithDueWork(MAX_TENANTS_PER_WAKE, registry.types())
        .concatMap(tenant ->
            processTenant(tenant)
                .onErrorResume(error -> {
                  log.warn(
                      "Processing work for tenant {} failed: {}",
                      tenant.value(),
                      SafeFailure.describe(error));
                  return Mono.just(0L);
                }))
        .reduce(0L, Long::sum);
  }

  /**
   * Dispatches up to one batch for the tenant under that tenant's scope. Items are leased one at a
   * time, each immediately before its dispatch, so a lease never ticks while the item waits behind
   * others in the batch; the batch size only bounds how many items one wake-up handles.
   */
  public Mono<Long> processTenant(TenantId tenant) {
    ScopeContext scope = ServiceIdentity.backendScope(tenant);
    return transactions
        .inTransaction(current -> repository.failExhaustedExpiredLeases(REASON_LEASE_EXHAUSTED))
        .thenMany(Flux.range(1, policy.claimBatchSize()))
        .concatMap(slot -> claimNext().map(Optional::of).defaultIfEmpty(Optional.empty()))
        .takeWhile(Optional::isPresent)
        .map(Optional::orElseThrow)
        .concatMap(this::dispatch)
        .count()
        .contextWrite(Scopes.bind(scope));
  }

  private Mono<Dispatch> claimNext() {
    return transactions
        .inTransaction(current ->
            repository.claim(1, policy.leaseDuration(), leaseOwner, registry.types()).next())
        .map(claimed -> new Dispatch(claimed, System.nanoTime()));
  }

  private Mono<UUID> dispatch(Dispatch dispatch) {
    WorkItem item = dispatch.item();
    return registry
        .find(item.type())
        .map(handler -> authorizeAndRun(dispatch, handler))
        // Unreachable while claims are limited to registered types; kept as the fail-safe answer.
        .orElseGet(() -> recordFailure(dispatch, REASON_UNREGISTERED, false))
        .thenReturn(item.id());
  }

  private Mono<Void> authorizeAndRun(Dispatch dispatch, WorkHandler handler) {
    WorkItem item = dispatch.item();
    return Mono.defer(() -> authorization.recheck(item, handler.registration()))
        .timeout(dispatch.remaining(policy.handlerDeadline()))
        .onErrorResume(error -> {
          log.warn(
              "Authorization recheck for work type {} could not decide: {}",
              item.type().value(),
              SafeFailure.describe(error));
          return Mono.just(DispatchDecision.UNDECIDED);
        })
        .defaultIfEmpty(DispatchDecision.UNDECIDED)
        .flatMap(decision ->
            switch (decision) {
              case ALLOW -> run(dispatch, handler);
              case DENY -> deny(dispatch);
              case UNDECIDED -> release(dispatch, REASON_AUTHORIZATION_UNDECIDED);
            });
  }

  private Mono<Void> run(Dispatch dispatch, WorkHandler handler) {
    WorkItem item = dispatch.item();
    return transactions
        .inTransaction(current ->
            repository
                .limitStatementTime(policy.statementTimeout())
                .then(Mono.defer(() -> handler.handle(item)))
                .timeout(
                    dispatch.remaining(policy.handlerDeadline()),
                    Mono.defer(() -> Mono.error(new HandlerDeadlineExceededException())))
                .switchIfEmpty(Mono.error(NoEffectOutcomeException::new))
                .flatMap(outcome -> completeFenced(dispatch, outcome)))
        .doOnNext(outcome ->
            log.debug(
                "Work item {} ({}) finished with effect {}",
                item.id(),
                item.type().value(),
                outcome.getClass().getSimpleName()))
        .then()
        .onErrorResume(
            StaleLeaseException.class,
            stale -> {
              log.info(
                  "Work item {} ({}) lost its lease before completion; the write changed nothing",
                  item.id(),
                  item.type().value());
              return Mono.empty();
            })
        // One resume for every other failure: the reason is derived first, so a failure of the
        // failure write itself propagates instead of replacing a typed reason with its own class.
        .onErrorResume(error ->
            recordFailure(dispatch, reasonFor(error), error instanceof NonRetryableWorkException));
  }

  private static String reasonFor(Throwable error) {
    if (error instanceof HandlerDeadlineExceededException) {
      return REASON_DEADLINE_EXCEEDED;
    }
    if (error instanceof NoEffectOutcomeException) {
      return REASON_NO_EFFECT_OUTCOME;
    }
    return SafeFailure.describe(error);
  }

  private Mono<EffectOutcome> completeFenced(Dispatch dispatch, EffectOutcome outcome) {
    UUID id = dispatch.item().id();
    return repository
        .complete(id, dispatch.leaseToken(), outcome)
        .flatMap(current -> current ? Mono.just(outcome) : Mono.error(new StaleLeaseException(id)));
  }

  private Mono<Void> deny(Dispatch dispatch) {
    WorkItem item = dispatch.item();
    return transactions
        .inTransaction(current ->
            repository.deny(item.id(), dispatch.leaseToken(), REASON_AUTHORIZATION_DENIED))
        .doOnNext(
            written -> logWrite(written, item, "denied at dispatch", REASON_AUTHORIZATION_DENIED))
        .then();
  }

  /** The attempt never started, so it is given back without counting (AC7, fail closed). */
  private Mono<Void> release(Dispatch dispatch, String safeReason) {
    WorkItem item = dispatch.item();
    return transactions
        .inTransaction(current ->
            repository.release(item.id(), dispatch.leaseToken(), safeReason, policy.backoffBase()))
        .doOnNext(written -> logWrite(written, item, "blocked and released", safeReason))
        .then();
  }

  private Mono<Void> recordFailure(Dispatch dispatch, String safeReason, boolean nonRetryable) {
    WorkItem item = dispatch.item();
    boolean terminal = nonRetryable || item.lastAttempt();
    return transactions
        .inTransaction(current ->
            repository.fail(
                item.id(),
                dispatch.leaseToken(),
                safeReason,
                policy.backoffFor(item.attempt()),
                terminal))
        .doOnNext(written -> {
          logWrite(
              written, item, terminal ? "failed terminally" : "scheduled for retry", safeReason);
          if (written && !terminal && policy.exhausted(item.attempt())) {
            log.warn(
                "Work item {} ({}) has used {} attempts, reaching or passing the configured {}, and is"
                    + " still being retried under its own limit: {}",
                item.id(),
                item.type().value(),
                item.attempt(),
                policy.maxAttempts(),
                safeReason);
          }
        })
        .then();
  }

  private static void logWrite(boolean written, WorkItem item, String outcome, String reason) {
    if (written) {
      log.info(
          "Work item {} ({}) {} after attempt {}/{}: {}",
          item.id(),
          item.type().value(),
          outcome,
          item.attempt(),
          item.maxAttempts(),
          reason);
    } else {
      log.info(
          "Work item {} ({}) lost its lease; the {} write was rejected and changed nothing",
          item.id(),
          item.type().value(),
          outcome);
    }
  }

  /**
   * A claimed item plus the moment (monotonic JVM clock) its claim returned, so every bound of the
   * dispatch counts from the claim rather than from the step that applies it. The database's lease
   * expiry is not used here: the two clocks may differ.
   */
  private record Dispatch(ClaimedWork claimed, long claimedAtNanos) {

    WorkItem item() {
      return claimed.item();
    }

    UUID leaseToken() {
      return claimed.leaseToken();
    }

    /**
     * What is left of {@code budget} since the claim; at least one millisecond, so it still fires.
     */
    Duration remaining(Duration budget) {
      Duration elapsed = Duration.ofNanos(System.nanoTime() - claimedAtNanos);
      Duration remaining = budget.minus(elapsed);
      return remaining.compareTo(Duration.ofMillis(1)) < 0 ? Duration.ofMillis(1) : remaining;
    }
  }

  /** The handler was cancelled at its deadline; recorded as {@value #REASON_DEADLINE_EXCEEDED}. */
  static final class HandlerDeadlineExceededException extends TimeoutException {
    private static final long serialVersionUID = 1L;

    HandlerDeadlineExceededException() {
      super(REASON_DEADLINE_EXCEEDED);
    }
  }

  /** Raised when a handler completes empty; only the class name is ever persisted. */
  static final class NoEffectOutcomeException extends IllegalStateException {
    private static final long serialVersionUID = 1L;

    NoEffectOutcomeException() {
      super(REASON_NO_EFFECT_OUTCOME);
    }
  }
}
