package com.aisquad.owlmast.jobs.adapter.scheduling;

import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.util.Objects;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import reactor.core.publisher.Mono;

/**
 * The only wake-up source for durable work (AD-6, AC9): in-process Spring scheduling with a fixed
 * delay, starting immediately after the context is ready so a new instance recovers work left by
 * the previous one without manual action (AC6). The reactive return type lets Spring subscribe and
 * wait for the run, with no blocking and no detached subscription. The two delays are read from the
 * same {@code owlmast.jobs.*} keys that {@code JobsProperties} binds and validates at start-up, so
 * an invalid value fails the context before this annotation is ever evaluated.
 */
@Slf4j
public final class WorkScheduler {

  private final WorkProcessor processor;

  WorkScheduler(WorkProcessor processor) {
    this.processor = Objects.requireNonNull(processor, "processor");
  }

  @Scheduled(
      initialDelayString = "${owlmast.jobs.initial-delay:PT0S}",
      fixedDelayString = "${owlmast.jobs.poll-interval:PT1S}")
  public Mono<Void> wake() {
    return processor
        .runOnce()
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
}
