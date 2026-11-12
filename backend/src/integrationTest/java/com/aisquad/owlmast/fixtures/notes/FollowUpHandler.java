package com.aisquad.owlmast.fixtures.notes;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;
import reactor.core.publisher.Mono;

/**
 * Fixture handler registered as tenant-internal system work. Its default behaviour applies one
 * external effect through the item's idempotency key; tests swap the behaviour to inject faults,
 * lease loss or uncertain outcomes. Every invocation records the scope it ran under (AC8).
 */
public final class FollowUpHandler implements WorkHandler {

  public static final WorkType TYPE = WorkType.of("fixture.follow-up");

  /** What one invocation observed. */
  public record Invocation(UUID itemId, String itemTenant, ScopeContext scope, int attempt) {}

  private final EffectStore effects;
  private final AtomicReference<Function<WorkItem, Mono<EffectOutcome>>> behaviour;
  private final AtomicBoolean once = new AtomicBoolean();
  private final List<Invocation> invocations = new CopyOnWriteArrayList<>();

  public FollowUpHandler(EffectStore effects) {
    this.effects = effects;
    this.behaviour = new AtomicReference<>(this::applyEffect);
  }

  @Override
  public WorkRegistration registration() {
    return WorkRegistration.tenantInternal(TYPE);
  }

  @Override
  public Mono<EffectOutcome> handle(WorkItem item) {
    return Scopes.current()
        .flatMap(scope -> {
          invocations.add(new Invocation(item.id(), item.tenant().value(), scope, item.attempt()));
          return Mono.defer(() -> behaviour.get().apply(item));
        });
  }

  /** Default behaviour: the external effect, deduplicated by the idempotency key. */
  public Mono<EffectOutcome> applyEffect(WorkItem item) {
    return Mono.fromCallable(() -> {
      effects.apply(item.idempotencyKey());
      return EffectOutcome.applied(item.idempotencyKey());
    });
  }

  public void behave(Function<WorkItem, Mono<EffectOutcome>> replacement) {
    behaviour.set(replacement);
  }

  /** Runs {@code first} for the next invocation only, then returns to the default behaviour. */
  public void behaveOnce(Function<WorkItem, Mono<EffectOutcome>> first) {
    once.set(true);
    behaviour.set(item -> once.compareAndSet(true, false) ? first.apply(item) : applyEffect(item));
  }

  public void reset() {
    behaviour.set(this::applyEffect);
    once.set(false);
    invocations.clear();
  }

  public List<Invocation> invocations() {
    return List.copyOf(invocations);
  }
}
