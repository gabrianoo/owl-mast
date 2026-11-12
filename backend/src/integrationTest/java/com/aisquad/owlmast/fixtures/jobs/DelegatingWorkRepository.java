package com.aisquad.owlmast.fixtures.jobs;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.FailedWorkItem;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.port.Claim;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.Duration;
import java.util.Set;
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/** Plain delegation, for test fixtures that change one repository call. */
public abstract class DelegatingWorkRepository implements WorkRepository {
  private final WorkRepository delegate;

  protected DelegatingWorkRepository(WorkRepository delegate) {
    this.delegate = delegate;
  }

  @Override
  public Mono<Long> failExhaustedExpiredLeases(String safeReason) {
    return delegate.failExhaustedExpiredLeases(safeReason);
  }

  @Override
  public Mono<Void> limitStatementTime(Duration timeout) {
    return delegate.limitStatementTime(timeout);
  }

  @Override
  public Mono<UUID> insert(
      UUID id,
      EnqueueRequest request,
      int contractVersion,
      int maxAttempts,
      PrincipalId enqueuedBy) {
    return delegate.insert(id, request, contractVersion, maxAttempts, enqueuedBy);
  }

  @Override
  public Flux<Claim> claim(
      int limit, Duration lease, String leaseOwner, UUID leaseToken, Set<WorkType> types) {
    return delegate.claim(limit, lease, leaseOwner, leaseToken, types);
  }

  @Override
  public Mono<Integer> release(
      UUID id, UUID leaseToken, String safeReason, Duration backoffBase, Duration backoffCap) {
    return delegate.release(id, leaseToken, safeReason, backoffBase, backoffCap);
  }

  @Override
  public Mono<Long> giveBack(UUID leaseToken, String safeReason) {
    return delegate.giveBack(leaseToken, safeReason);
  }

  @Override
  public Mono<Boolean> complete(UUID id, UUID leaseToken, EffectOutcome outcome) {
    return delegate.complete(id, leaseToken, outcome);
  }

  @Override
  public Mono<Boolean> fail(
      UUID id, UUID leaseToken, String safeReason, Duration backoff, boolean terminal) {
    return delegate.fail(id, leaseToken, safeReason, backoff, terminal);
  }

  @Override
  public Mono<Boolean> deny(UUID id, UUID leaseToken, String safeReason) {
    return delegate.deny(id, leaseToken, safeReason);
  }

  @Override
  public Flux<TenantId> tenantsWithDueWork(
      int limit, Set<WorkType> types, Duration statementLimit) {
    return delegate.tenantsWithDueWork(limit, types, statementLimit);
  }

  @Override
  public Flux<FailedWorkItem> listTerminalFailures(int limit) {
    return delegate.listTerminalFailures(limit);
  }
}
