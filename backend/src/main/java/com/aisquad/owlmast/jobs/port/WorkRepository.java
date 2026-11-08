package com.aisquad.owlmast.jobs.port;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.FailedWorkItem;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.Duration;
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * Persistence the jobs owner needs. Every method except {@link #tenantsWithDueWork(int)} runs
 * inside a scoped transaction and filters on the tenant bound to that transaction, never on a
 * parameter; lease-fenced writes return {@code false} when the lease is no longer current, having
 * changed nothing.
 */
public interface WorkRepository {

  Mono<UUID> insert(
      UUID id,
      EnqueueRequest request,
      int contractVersion,
      int maxAttempts,
      PrincipalId enqueuedBy);

  /** Claims due pending items and expired-lease running items of the bound tenant, oldest first. */
  Flux<ClaimedWork> claim(int limit, Duration lease, String leaseOwner);

  /** Running items of the bound tenant whose lease expired after their last permitted attempt. */
  Mono<Long> failExhaustedExpiredLeases(String safeReason);

  Mono<Boolean> complete(UUID id, UUID leaseToken, EffectOutcome outcome);

  /** Records a failed attempt: back to PENDING after {@code backoff}, or terminal FAILED. */
  Mono<Boolean> fail(
      UUID id, UUID leaseToken, String safeReason, Duration backoff, boolean terminal);

  Mono<Boolean> deny(UUID id, UUID leaseToken, String safeReason);

  /** Identifier-only discovery across tenants, outside any scope; drives per-tenant processing. */
  Flux<TenantId> tenantsWithDueWork(int limit);

  Flux<FailedWorkItem> listTerminalFailures(int limit);
}
