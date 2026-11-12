package com.aisquad.owlmast.jobs.port;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.FailedWorkItem;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.Duration;
import java.util.Set;
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * Persistence the jobs owner needs. Every method except {@link #tenantsWithDueWork(int, Set,
 * Duration)} runs inside a scoped transaction and filters on the tenant bound to that transaction,
 * never on a parameter; lease-fenced writes return {@code false} when the lease is no longer
 * current, having changed nothing. A lease token exists only while an item is {@code RUNNING}:
 * every write that leaves that status clears it.
 */
public interface WorkRepository {

  Mono<UUID> insert(
      UUID id,
      EnqueueRequest request,
      int contractVersion,
      int maxAttempts,
      PrincipalId enqueuedBy);

  /**
   * Claims due pending items and expired-lease running items of the bound tenant, oldest first,
   * limited to the given work types and to items written with a contract version this build
   * supports, so an instance never takes work it cannot run (a rolling deploy with a new work type
   * or a newer contract version). A claimed row that cannot be decoded into a {@code WorkItem} is
   * recorded as terminal {@code FAILED} under its new lease and emitted as {@link
   * Claim.Undecodable}, so one poison row never stalls the tenant's queue and the caller can tell a
   * skipped row from an empty queue.
   *
   * <p>The caller chooses the lease token of the call, so it can still give the claim back ({@link
   * #giveBack(UUID, String)}) when the claim committed but its answer never arrived. A reclaim of
   * an expired lease ends the item's streak of consecutive releases: the attempt it replaces was
   * not a release.
   */
  Flux<Claim> claim(
      int limit, Duration lease, String leaseOwner, UUID leaseToken, Set<WorkType> types);

  /** Running items of the bound tenant whose lease expired after their last permitted attempt. */
  Mono<Long> failExhaustedExpiredLeases(String safeReason);

  Mono<Boolean> complete(UUID id, UUID leaseToken, EffectOutcome outcome);

  /** Records a failed attempt: back to PENDING after {@code backoff}, or terminal FAILED. */
  Mono<Boolean> fail(
      UUID id, UUID leaseToken, String safeReason, Duration backoff, boolean terminal);

  /**
   * Gives a claimed item back without counting the attempt because the processor could not start it
   * (an undecided authorization recheck): back to PENDING, the attempt count restored, the reason
   * recorded and the consecutive-release count incremented. The delay doubles with every
   * consecutive release from {@code backoffBase} up to {@code backoffCap}, so an outage of the
   * deciding component never exhausts the item's budget and never becomes a fixed-rate loop. Emits
   * the new consecutive-release count, or nothing when the lease is no longer current.
   */
  Mono<Integer> release(
      UUID id, UUID leaseToken, String safeReason, Duration backoffBase, Duration backoffCap);

  /**
   * Gives back at once and uncounted what the claim made with {@code leaseToken} still holds,
   * because its dispatch was cancelled (a graceful shutdown): back to PENDING and due immediately,
   * the attempt count restored, the reason recorded, the consecutive-release count unchanged. The
   * token alone identifies the claim, so this also works when the claimed row never reached the
   * caller. A claim that is still committing is waited for (within the statement bound of the
   * transaction), so the give-back never misses a commit that lands after it looked. Emits the
   * number of items given back; zero when the lease is no longer current or the claim never
   * committed.
   */
  Mono<Long> giveBack(UUID leaseToken, String safeReason);

  Mono<Boolean> deny(UUID id, UUID leaseToken, String safeReason);

  /** Bounds every later statement of the current transaction on the server side. */
  Mono<Void> limitStatementTime(Duration timeout);

  /**
   * Ends the current transaction on the server once {@code remaining} has passed from now, whatever
   * it is doing then and whenever its current statement started: the server closes the session, so
   * nothing of the transaction can commit afterwards.
   */
  Mono<Void> limitTransactionTime(Duration remaining);

  /**
   * Identifier-only discovery across tenants, outside any scope; drives per-tenant processing. Only
   * work this instance can claim counts (the given types, a supported contract version). Tenants
   * are ordered by their longest-waiting due item, so a bounded wake-up never starves the tenants
   * that sort after the limit. Runs in a read transaction of its own whose statements the server
   * cancels after {@code statementLimit}, so a query the caller gave up on does not keep running.
   */
  Flux<TenantId> tenantsWithDueWork(int limit, Set<WorkType> types, Duration statementLimit);

  Flux<FailedWorkItem> listTerminalFailures(int limit);
}
