package com.aisquad.owlmast.jobs.adapter.scheduling;

import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;
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
 *
 * <p>Database precondition (E01-R-06): a wake-up claims nothing unless the database server answers
 * as supported. Handler transactions are bounded with {@code transaction_timeout}, which PostgreSQL
 * 17 introduced; on an older server every handler would fail, bounded work would end {@code FAILED}
 * for a reason no retry cures and audit publication would retry forever. Readiness being DOWN for
 * the same reason does not stop a scheduled task, so the wake-up checks for itself, every time: the
 * server behind the same address can change while the process runs (a failover, a repoint), so a
 * yes is not kept. While the precondition answers no, cannot be read or takes longer than {@link
 * #PRECONDITION_TIMEOUT}, nothing is claimed; the refusal is logged when it starts, not at every
 * wake-up. A stop also ends a precondition read in flight.
 */
@Slf4j
public final class WorkScheduler implements SmartLifecycle {

  private final WorkProcessor processor;
  private final Supplier<Mono<Boolean>> databaseSupported;
  private final Duration preconditionTimeout;

  /** How long one wake-up waits for the database precondition before it counts as not met. */
  static final Duration PRECONDITION_TIMEOUT = Duration.ofSeconds(10);

  private final AtomicBoolean refusing = new AtomicBoolean();
  private final AtomicBoolean running = new AtomicBoolean();
  private final AtomicReference<Sinks.One<Boolean>> stopping = new AtomicReference<>(Sinks.one());

  /**
   * @param databaseSupported whether the database server can run durable work; asked at every
   *     wake-up
   */
  WorkScheduler(WorkProcessor processor, Supplier<Mono<Boolean>> databaseSupported) {
    this(processor, databaseSupported, PRECONDITION_TIMEOUT);
  }

  WorkScheduler(
      WorkProcessor processor,
      Supplier<Mono<Boolean>> databaseSupported,
      Duration preconditionTimeout) {
    this.processor = Objects.requireNonNull(processor, "processor");
    this.databaseSupported = Objects.requireNonNull(databaseSupported, "databaseSupported");
    this.preconditionTimeout = Objects.requireNonNull(preconditionTimeout, "preconditionTimeout");
  }

  @Scheduled(
      initialDelayString = "${owlmast.jobs.initial-delay:PT0S}",
      fixedDelayString = "${owlmast.jobs.poll-interval:PT1S}")
  public Mono<Void> wake() {
    // Spring asks for this publisher once and subscribes to it at every wake-up, so the lifecycle
    // state is read per subscription.
    return Mono.defer(() -> {
      if (!running.get()) {
        return Mono.empty();
      }
      Sinks.One<Boolean> stop = stopping.get();
      return confirmedSupported()
          .takeUntilOther(stop.asMono())
          .flatMap(confirmed -> confirmed && running.get() ? wakeUp() : Mono.empty());
    });
  }

  private Mono<Boolean> confirmedSupported() {
    return Mono.defer(databaseSupported)
        .timeout(preconditionTimeout)
        .defaultIfEmpty(false)
        .doOnNext(answer -> {
          if (answer) {
            if (refusing.compareAndSet(true, false)) {
              log.info(
                  "Durable work resumes: the database server is a supported PostgreSQL version");
            }
          } else if (refusing.compareAndSet(false, true)) {
            log.warn(
                "Durable work is not started: the database server is not a supported PostgreSQL"
                    + " version, or its schema baseline cannot be read. No work is claimed until"
                    + " it is");
          }
        })
        .onErrorResume(error -> {
          if (refusing.compareAndSet(false, true)) {
            log.warn(
                "Durable work is not started: the database precondition could not be read: {}",
                SafeFailure.describe(error));
          }
          return Mono.just(false);
        });
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
