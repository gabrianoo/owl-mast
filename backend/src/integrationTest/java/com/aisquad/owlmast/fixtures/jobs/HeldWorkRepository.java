package com.aisquad.owlmast.fixtures.jobs;

import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.port.Claim;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * Delegates everything, but the first matching call of one kind does not reach the database until
 * {@link #release()} is called: it never answers while held, as when the network partitions after
 * the request was sent. Later calls of that kind delegate at once. Also records every server-side
 * statement bound and counts the claims.
 */
public final class HeldWorkRepository extends DelegatingWorkRepository {

  /** The repository calls a fixture can hold. */
  public enum Call {
    DISCOVERY,
    SWEEP,
    CLAIM,
    RELEASE,
    FAIL,
    DENY,
    GIVE_BACK
  }

  private final Call held;
  private final CompletableFuture<Void> entered = new CompletableFuture<>();
  private final CompletableFuture<Void> released = new CompletableFuture<>();
  private final AtomicBoolean used = new AtomicBoolean();
  private final AtomicInteger claims = new AtomicInteger();
  private final List<Duration> statementLimits = new CopyOnWriteArrayList<>();

  public HeldWorkRepository(WorkRepository delegate, Call held) {
    super(delegate);
    this.held = held;
  }

  /** Completes when the held call was made. */
  public CompletableFuture<Void> entered() {
    return entered;
  }

  /** Lets the held call go on to the database. */
  public void release() {
    released.complete(null);
  }

  public int claims() {
    return claims.get();
  }

  public List<Duration> statementLimits() {
    return List.copyOf(statementLimits);
  }

  private Mono<Void> hold(Call call) {
    if (call != held || !used.compareAndSet(false, true)) {
      return Mono.empty();
    }
    entered.complete(null);
    // fromCompletionStage: a cancelled call must not complete the future for everyone else.
    return Mono.fromCompletionStage(released);
  }

  @Override
  public Mono<Void> limitStatementTime(Duration timeout) {
    statementLimits.add(timeout);
    return super.limitStatementTime(timeout);
  }

  @Override
  public Flux<TenantId> tenantsWithDueWork(
      int limit, Set<WorkType> types, Duration statementLimit) {
    return Flux.defer(() ->
        hold(Call.DISCOVERY).thenMany(super.tenantsWithDueWork(limit, types, statementLimit)));
  }

  @Override
  public Mono<Long> failExhaustedExpiredLeases(String safeReason) {
    return Mono.defer(() -> hold(Call.SWEEP).then(super.failExhaustedExpiredLeases(safeReason)));
  }

  @Override
  public Flux<Claim> claim(
      int limit, Duration lease, String leaseOwner, UUID leaseToken, Set<WorkType> types) {
    return Flux.defer(() -> {
      claims.incrementAndGet();
      return hold(Call.CLAIM).thenMany(super.claim(limit, lease, leaseOwner, leaseToken, types));
    });
  }

  @Override
  public Mono<Integer> release(
      UUID id, UUID leaseToken, String safeReason, Duration backoffBase, Duration backoffCap) {
    return Mono.defer(() ->
        hold(Call.RELEASE)
            .then(super.release(id, leaseToken, safeReason, backoffBase, backoffCap)));
  }

  @Override
  public Mono<Boolean> fail(
      UUID id, UUID leaseToken, String safeReason, Duration backoff, boolean terminal) {
    return Mono.defer(
        () -> hold(Call.FAIL).then(super.fail(id, leaseToken, safeReason, backoff, terminal)));
  }

  @Override
  public Mono<Boolean> deny(UUID id, UUID leaseToken, String safeReason) {
    return Mono.defer(() -> hold(Call.DENY).then(super.deny(id, leaseToken, safeReason)));
  }

  @Override
  public Mono<Long> giveBack(UUID leaseToken, String safeReason) {
    return Mono.defer(() -> hold(Call.GIVE_BACK).then(super.giveBack(leaseToken, safeReason)));
  }
}
