package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.DispatchAuthorization;
import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.NonRetryableWorkException;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.Claim;
import com.aisquad.owlmast.jobs.port.ClaimedWork;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.platform.scope.ServiceIdentity;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeoutException;
import java.util.function.Function;
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
 *       types, a supported contract version); expired leases are reclaimed by the next claim. A row
 *       that cannot be decoded is failed terminally by the claim and uses one slot of the batch
 *       without ending it.
 *   <li>The authorization recheck runs before every dispatch; DENY is terminal, UNDECIDED and
 *       errors (a recheck that has not allowed the dispatch within {@link
 *       RetryPolicy#recheckDeadline()} included) release the item for a later attempt without
 *       counting one (AC7). Consecutive releases back off exponentially up to the cap and are
 *       logged at WARN from the configured attempt limit on.
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
 *   <li>Every step outside the handler (discovery, sweep, claim, release, deny and failure writes)
 *       is bounded by {@link RetryPolicy#stepTimeout()} on the client and, inside a transaction, on
 *       the server, and the handler's transaction as a whole ends with the lease, so one stalled
 *       statement or commit fails its step instead of stopping every later wake-up.
 *   <li>A dispatch that is cancelled (a graceful shutdown cancels the scheduled wake-up) gives its
 *       item back at once and uncounted under the lease it holds ({@value
 *       #REASON_DISPATCH_CANCELLED}); {@link #quiesce()} completes when those writes have ended.
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
  static final String REASON_DISPATCH_CANCELLED = "dispatch-cancelled";

  /** Upper bound of a give-back after a cancelled dispatch, so a shutdown never waits a lease. */
  static final Duration GIVE_BACK_TIMEOUT = Duration.ofSeconds(10);

  static final int MAX_TENANTS_PER_WAKE = 100;

  private final ScopedTransactions transactions;
  private final WorkRepository repository;
  private final HandlerRegistry registry;
  private final DispatchAuthorization authorization;
  private final RetryPolicy policy;
  private final String leaseOwner;
  private final Set<Mono<Void>> pendingGiveBacks = ConcurrentHashMap.newKeySet();

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

  /**
   * Completes when every give-back started by a cancelled dispatch has ended (written, rejected or
   * failed). The scheduler waits for it during a graceful shutdown, before the connections close.
   */
  public Mono<Void> quiesce() {
    return Mono.defer(() -> Mono.when(List.copyOf(pendingGiveBacks)));
  }

  /** Processes every tenant with due work once; returns the number of items dispatched. */
  public Mono<Long> runOnce() {
    return repository
        .tenantsWithDueWork(MAX_TENANTS_PER_WAKE, registry.types())
        .collectList()
        .timeout(policy.stepTimeout())
        .flatMapMany(Flux::fromIterable)
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
   * others in the batch; the batch size only bounds how many slots one wake-up handles. A slot
   * whose claimed row could not be decoded is skipped; the batch ends early only when no due row
   * was found.
   */
  public Mono<Long> processTenant(TenantId tenant) {
    ScopeContext scope = ServiceIdentity.backendScope(tenant);
    return step(current -> repository.failExhaustedExpiredLeases(REASON_LEASE_EXHAUSTED))
        .thenMany(Flux.range(1, policy.claimBatchSize()))
        .concatMap(slot -> claimNext())
        .takeWhile(Slot::dueRowFound)
        .concatMap(slot -> slot.dispatch().map(this::dispatch).orElseGet(Mono::empty))
        .count()
        .contextWrite(Scopes.bind(scope));
  }

  private Mono<Slot> claimNext() {
    return step(current ->
            repository.claim(1, policy.leaseDuration(), leaseOwner, registry.types()).next())
        .map(claim ->
            switch (claim) {
              case ClaimedWork work -> Slot.of(new Dispatch(work, System.nanoTime()));
              case Claim.Undecodable skipped -> Slot.SKIPPED;
            })
        .defaultIfEmpty(Slot.NO_DUE_WORK);
  }

  /**
   * One processor step outside the handler, in its own scoped transaction: every statement is
   * bounded on the server and the whole step on the client by {@link RetryPolicy#stepTimeout()}.
   */
  private <T> Mono<T> step(Function<ScopeContext, Mono<T>> work) {
    Duration bound = policy.stepTimeout();
    return transactions
        .inTransaction(current ->
            repository.limitStatementTime(bound).then(Mono.defer(() -> work.apply(current))))
        .timeout(bound);
  }

  private Mono<UUID> dispatch(Dispatch dispatch) {
    WorkItem item = dispatch.item();
    return registry
        .find(item.type())
        .map(handler -> authorizeAndRun(dispatch, handler))
        // Unreachable while claims are limited to registered types; kept as the fail-safe answer.
        .orElseGet(() -> recordFailure(dispatch, REASON_UNREGISTERED, false))
        .thenReturn(item.id())
        .doOnCancel(() -> giveBackCancelled(dispatch));
  }

  private Mono<Void> authorizeAndRun(Dispatch dispatch, WorkHandler handler) {
    WorkItem item = dispatch.item();
    return Mono.defer(() -> authorization.recheck(item, handler.registration()))
        .timeout(dispatch.remaining(policy.recheckDeadline()))
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
              // An answer that arrived past the recheck's share is not charged to the handler.
              case ALLOW ->
                  dispatch.elapsed().compareTo(policy.recheckDeadline()) > 0
                      ? release(dispatch, REASON_AUTHORIZATION_UNDECIDED)
                      : run(dispatch, handler);
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
        // The transaction as a whole (begin, completion write, commit) ends with the lease: past
        // it no write of this dispatch can count, so a commit that never answers must not hold
        // the wake-up. The failure write below is then rejected by the fence.
        .timeout(dispatch.remaining(policy.leaseDuration()))
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
    return step(current ->
            repository.deny(item.id(), dispatch.leaseToken(), REASON_AUTHORIZATION_DENIED))
        .doOnNext(
            written -> logWrite(written, item, "denied at dispatch", REASON_AUTHORIZATION_DENIED))
        .then();
  }

  /**
   * The attempt never started, so it is given back without counting (AC7, fail closed). The delay
   * doubles with every consecutive release up to the backoff cap; from the configured attempt limit
   * on, every further release is logged at WARN, because the item never becomes terminal.
   */
  private Mono<Void> release(Dispatch dispatch, String safeReason) {
    WorkItem item = dispatch.item();
    return step(current ->
            repository
                .release(
                    item.id(),
                    dispatch.leaseToken(),
                    safeReason,
                    policy.backoffBase(),
                    policy.backoffCap())
                .map(Optional::of)
                .defaultIfEmpty(Optional.empty()))
        .doOnNext(releases -> {
          logWrite(releases.isPresent(), item, "blocked and released", safeReason);
          releases
              .filter(policy::exhausted)
              .ifPresent(count ->
                  log.warn(
                      "Work item {} ({}) has been released {} times in a row without a dispatch"
                          + " decision and is still waiting: {}",
                      item.id(),
                      item.type().value(),
                      count,
                      safeReason));
        })
        .then();
  }

  /**
   * The dispatch was cancelled from outside (a graceful shutdown): the item is handed back at once
   * and uncounted in a write of its own, fenced by the lease this dispatch holds, so a write that
   * already left {@code RUNNING} is not touched. Without it the item would stay {@code RUNNING}
   * until its lease ran out and the reclaim would count an attempt the item never failed.
   */
  private void giveBackCancelled(Dispatch dispatch) {
    WorkItem item = dispatch.item();
    Duration bound =
        policy.stepTimeout().compareTo(GIVE_BACK_TIMEOUT) < 0
            ? policy.stepTimeout()
            : GIVE_BACK_TIMEOUT;
    Mono<Void> write =
        step(current ->
                repository.giveBack(item.id(), dispatch.leaseToken(), REASON_DISPATCH_CANCELLED))
            .timeout(bound)
            .doOnNext(written ->
                logWrite(written, item, "given back uncounted", REASON_DISPATCH_CANCELLED))
            .then()
            .onErrorResume(error -> {
              log.warn(
                  "Work item {} ({}) could not be given back after its dispatch was cancelled and"
                      + " waits for its lease to expire: {}",
                  item.id(),
                  item.type().value(),
                  SafeFailure.describe(error));
              return Mono.empty();
            })
            .contextWrite(Scopes.bind(ServiceIdentity.backendScope(item.tenant())))
            .cache();
    pendingGiveBacks.add(write);
    write.doFinally(signal -> pendingGiveBacks.remove(write)).subscribe();
  }

  private Mono<Void> recordFailure(Dispatch dispatch, String safeReason, boolean nonRetryable) {
    WorkItem item = dispatch.item();
    boolean terminal = nonRetryable || item.lastAttempt();
    return step(current ->
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

    Duration elapsed() {
      return Duration.ofNanos(System.nanoTime() - claimedAtNanos);
    }

    /**
     * What is left of {@code budget} since the claim; at least one millisecond, so it still fires.
     */
    Duration remaining(Duration budget) {
      Duration remaining = budget.minus(elapsed());
      return remaining.compareTo(Duration.ofMillis(1)) < 0 ? Duration.ofMillis(1) : remaining;
    }
  }

  /** One slot of a tenant's batch: no due row, a row skipped by the claim, or an item to run. */
  private record Slot(boolean dueRowFound, Optional<Dispatch> dispatch) {
    static final Slot NO_DUE_WORK = new Slot(false, Optional.empty());
    static final Slot SKIPPED = new Slot(true, Optional.empty());

    static Slot of(Dispatch dispatch) {
      return new Slot(true, Optional.of(dispatch));
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
