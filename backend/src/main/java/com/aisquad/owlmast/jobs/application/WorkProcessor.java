package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.DispatchAuthorization;
import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.EffectOutcome;
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
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import lombok.extern.slf4j.Slf4j;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * One wake-up of the durable-work processor (AD-6). Tenants with due work are discovered by
 * identifier only; each tenant's items are then claimed, authorized, run and completed inside
 * scoped transactions bound to that tenant under the backend service identity (AD-3, AC8).
 *
 * <ul>
 *   <li>Claiming is bounded and lease-based; expired leases are reclaimed by the next claim.
 *   <li>The authorization recheck runs before every dispatch; DENY is terminal, UNDECIDED and
 *       errors are recorded as a blocked attempt and retried with backoff (AC7).
 *   <li>The handler and the completion write share one transaction fenced by the lease token: a
 *       stale lease rolls back the handler's database effects and the write changes nothing (AC2).
 *   <li>Failed attempts persist the attempt count, a capped backoff and the exception class chain
 *       only; the last permitted attempt makes the item terminal (AC5).
 * </ul>
 */
@Slf4j
public final class WorkProcessor {

  static final String REASON_UNREGISTERED = "unregistered-work-type";
  static final String REASON_AUTHORIZATION_DENIED = "authorization-denied";
  static final String REASON_AUTHORIZATION_UNDECIDED = "authorization-undecided";
  static final String REASON_LEASE_EXHAUSTED = "lease-expired-attempts-exhausted";
  static final String REASON_NO_EFFECT_OUTCOME = "handler-returned-no-effect-outcome";
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
        .tenantsWithDueWork(MAX_TENANTS_PER_WAKE)
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

  private Mono<ClaimedWork> claimNext() {
    return transactions.inTransaction(
        current -> repository.claim(1, policy.leaseDuration(), leaseOwner).next());
  }

  private Mono<UUID> dispatch(ClaimedWork claimed) {
    WorkItem item = claimed.item();
    return registry
        .find(item.type())
        .map(handler -> authorizeAndRun(claimed, handler))
        .orElseGet(() -> recordFailure(claimed, REASON_UNREGISTERED))
        .thenReturn(item.id());
  }

  private Mono<Void> authorizeAndRun(ClaimedWork claimed, WorkHandler handler) {
    WorkItem item = claimed.item();
    return Mono.defer(() -> authorization.recheck(item, handler.registration()))
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
              case ALLOW -> run(claimed, handler);
              case DENY -> deny(claimed);
              case UNDECIDED -> recordFailure(claimed, REASON_AUTHORIZATION_UNDECIDED);
            });
  }

  private Mono<Void> run(ClaimedWork claimed, WorkHandler handler) {
    WorkItem item = claimed.item();
    return transactions
        .inTransaction(current ->
            Mono.defer(() -> handler.handle(item))
                .switchIfEmpty(Mono.error(NoEffectOutcomeException::new))
                .flatMap(outcome -> completeFenced(claimed, outcome)))
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
        .onErrorResume(error -> recordFailure(claimed, SafeFailure.describe(error)));
  }

  private Mono<EffectOutcome> completeFenced(ClaimedWork claimed, EffectOutcome outcome) {
    UUID id = claimed.item().id();
    return repository
        .complete(id, claimed.leaseToken(), outcome)
        .flatMap(current -> current ? Mono.just(outcome) : Mono.error(new StaleLeaseException(id)));
  }

  private Mono<Void> deny(ClaimedWork claimed) {
    WorkItem item = claimed.item();
    return transactions
        .inTransaction(current ->
            repository.deny(item.id(), claimed.leaseToken(), REASON_AUTHORIZATION_DENIED))
        .doOnNext(
            written -> logWrite(written, item, "denied at dispatch", REASON_AUTHORIZATION_DENIED))
        .then();
  }

  private Mono<Void> recordFailure(ClaimedWork claimed, String safeReason) {
    WorkItem item = claimed.item();
    boolean terminal = item.lastAttempt();
    return transactions
        .inTransaction(current ->
            repository.fail(
                item.id(),
                claimed.leaseToken(),
                safeReason,
                policy.backoffFor(item.attempt()),
                terminal))
        .doOnNext(written ->
            logWrite(
                written, item, terminal ? "failed terminally" : "scheduled for retry", safeReason))
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

  /** Raised when a handler completes empty; only the class name is ever persisted. */
  static final class NoEffectOutcomeException extends IllegalStateException {
    private static final long serialVersionUID = 1L;

    NoEffectOutcomeException() {
      super(REASON_NO_EFFECT_OUTCOME);
    }
  }
}
