package com.aisquad.owlmast.jobs.adapter.config;

import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * {@code owlmast.jobs.*}: retry, lease, claim and wake-up settings. Absent values fall back to the
 * contract defaults in {@link WorkItemContract}; {@code application.yaml} restates them.
 */
@ConfigurationProperties("owlmast.jobs")
public record JobsProperties(
    Integer maxAttempts,
    Duration backoffBase,
    Duration backoffCap,
    Duration leaseDuration,
    Integer claimBatchSize,
    Duration pollInterval) {

  public JobsProperties {
    maxAttempts = orDefault(maxAttempts, WorkItemContract.DEFAULT_MAX_ATTEMPTS);
    backoffBase = orDefault(backoffBase, WorkItemContract.DEFAULT_BACKOFF_BASE);
    backoffCap = orDefault(backoffCap, WorkItemContract.DEFAULT_BACKOFF_CAP);
    leaseDuration = orDefault(leaseDuration, WorkItemContract.DEFAULT_LEASE_DURATION);
    claimBatchSize = orDefault(claimBatchSize, WorkItemContract.DEFAULT_CLAIM_BATCH_SIZE);
    pollInterval = orDefault(pollInterval, WorkItemContract.DEFAULT_POLL_INTERVAL);
    if (pollInterval.isZero() || pollInterval.isNegative()) {
      throw new IllegalArgumentException("owlmast.jobs.poll-interval must be positive");
    }
  }

  public RetryPolicy policy() {
    return new RetryPolicy(maxAttempts, backoffBase, backoffCap, leaseDuration, claimBatchSize);
  }

  private static <T> T orDefault(T value, T fallback) {
    return Optional.ofNullable(value).orElse(fallback);
  }
}
