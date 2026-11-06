package com.aisquad.owlmast.platform.blocking;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * Bounds for unavoidable blocking SDK calls (AD-5): concurrent threads, calls queued per thread and
 * the per-call deadline.
 */
@ConfigurationProperties("owlmast.blocking")
public record BoundedBlockingProperties(
    @DefaultValue("8") int maxConcurrency,
    @DefaultValue("16") int maxQueuedPerThread,
    @DefaultValue("10s") Duration deadline) {

  public BoundedBlockingProperties {
    if (maxConcurrency < 1) {
      throw new IllegalArgumentException("owlmast.blocking.max-concurrency must be >= 1");
    }
    if (maxQueuedPerThread < 1) {
      throw new IllegalArgumentException("owlmast.blocking.max-queued-per-thread must be >= 1");
    }
    if (deadline == null || deadline.isZero() || deadline.isNegative()) {
      throw new IllegalArgumentException("owlmast.blocking.deadline must be positive");
    }
  }
}
