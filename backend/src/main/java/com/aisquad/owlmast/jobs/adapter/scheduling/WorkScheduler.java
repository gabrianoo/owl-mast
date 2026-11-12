package com.aisquad.owlmast.jobs.adapter.scheduling;

import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.annotation.Scheduled;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

/**
 * The only wake-up source for durable work (AD-6, AC9): in-process Spring scheduling with a fixed
 * delay, starting immediately after the context is ready so a new instance recovers work left by
 * the previous one without manual action (AC6). The reactive return type lets Spring subscribe and
 * wait for the run, with no blocking and no detached subscription. The two delays are read from the
 * same {@code owlmast.jobs.*} keys that {@code JobsProperties} binds and validates at start-up, so
 * an invalid value fails the context before this annotation is ever evaluated.
 *
 * <p>Graceful shutdown: as a {@link SmartLifecycle} this bean is stopped before any bean (and the
 * database connections) is destroyed. Stopping ends the wake-up in flight, which cancels its
 * dispatch; the processor then gives that item back at once and uncounted instead of leaving it
 * {@code RUNNING} until its lease expires. The stop completes only when that give-back has ended,
 * without blocking a thread, and a wake-up that fires afterwards claims nothing.
 */
@Slf4j
public final class WorkScheduler implements SmartLifecycle {

  private final WorkProcessor processor;
  private final AtomicBoolean running = new AtomicBoolean();
  private final AtomicReference<Sinks.One<Boolean>> stopping = new AtomicReference<>(Sinks.one());

  WorkScheduler(WorkProcessor processor) {
    this.processor = Objects.requireNonNull(processor, "processor");
  }

  @Scheduled(
      initialDelayString = "${owlmast.jobs.initial-delay:PT0S}",
      fixedDelayString = "${owlmast.jobs.poll-interval:PT1S}")
  public Mono<Void> wake() {
    // Spring asks for this publisher once and subscribes to it at every wake-up, so the lifecycle
    // state is read per subscription.
    return Mono.defer(() -> running.get() ? wakeUp() : Mono.empty());
  }

  private Mono<Void> wakeUp() {
    return processor
        .runOnce()
        .takeUntilOther(stopping.get().asMono())
        .doOnNext(dispatched -> {
          if (dispatched > 0) {
            log.debug("Processor wake-up dispatched {} work item(s)", dispatched);
          }
        })
        .then()
        .onErrorResume(error -> {
          log.warn("Processor wake-up failed: {}", SafeFailure.describe(error));
          return Mono.empty();
        });
  }

  @Override
  public void start() {
    stopping.set(Sinks.one());
    running.set(true);
  }

  /** Ends the wake-up in flight; its cancelled dispatch is given back by the processor. */
  @Override
  public void stop() {
    running.set(false);
    stopping.get().tryEmitValue(true);
  }

  /** Completes the stop once every give-back of a cancelled dispatch has ended. */
  @Override
  public void stop(Runnable callback) {
    stop();
    processor
        .quiesce()
        .onErrorResume(error -> {
          log.warn("Waiting for cancelled dispatches failed: {}", SafeFailure.describe(error));
          return Mono.empty();
        })
        .doFinally(signal -> callback.run())
        .subscribe();
  }

  @Override
  public boolean isRunning() {
    return running.get();
  }
}
