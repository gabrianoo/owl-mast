package com.aisquad.owlmast.platform.blocking;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.RejectedExecutionException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

/**
 * Runs unavoidable blocking work off the event loop with bounded concurrency, a bounded queue and a
 * deadline (AD-5). Blocking code receives what it needs as explicit arguments; the Reactor Context
 * (including the {@code ScopeContext}) is preserved for the operators around the call.
 */
public final class BoundedBlocking implements AutoCloseable {

  private final Scheduler scheduler;
  private final BoundedBlockingProperties properties;

  private BoundedBlocking(Scheduler scheduler, BoundedBlockingProperties properties) {
    this.scheduler = scheduler;
    this.properties = properties;
  }

  public static BoundedBlocking create(BoundedBlockingProperties properties) {
    Objects.requireNonNull(properties, "properties");
    Scheduler scheduler =
        Schedulers.newBoundedElastic(
            properties.maxConcurrency(), properties.maxQueuedPerThread(), "owlmast-blocking");
    return new BoundedBlocking(scheduler, properties);
  }

  /** Executes {@code blocking} within the configured bounds and the default deadline. */
  public <T> Mono<T> call(String operation, Callable<T> blocking) {
    return call(operation, properties.deadline(), blocking);
  }

  /** Executes {@code blocking} within the configured bounds and an explicit deadline. */
  public <T> Mono<T> call(String operation, Duration deadline, Callable<T> blocking) {
    Objects.requireNonNull(operation, "operation");
    Objects.requireNonNull(blocking, "blocking");
    return Mono.fromCallable(blocking)
        .subscribeOn(scheduler)
        .timeout(
            deadline, Mono.error(() -> new BlockingDeadlineExceededException(operation, deadline)))
        .onErrorMap(
            RejectedExecutionException.class,
            rejected ->
                new BlockingCapacityExceededException(
                    operation, properties.maxConcurrency(), properties.maxQueuedPerThread()));
  }

  @Override
  public void close() {
    scheduler.dispose();
  }
}
