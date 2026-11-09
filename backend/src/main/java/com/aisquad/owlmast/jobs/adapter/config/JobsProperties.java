package com.aisquad.owlmast.jobs.adapter.config;

import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import java.time.Duration;
import java.util.Optional;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * {@code owlmast.jobs.*}: retry, lease, claim and wake-up settings. Absent values fall back to the
 * contract defaults in {@link WorkItemContract}; {@code application.yaml} restates them. Every
 * setting the scheduler reads through a placeholder ({@code initial-delay}, {@code poll-interval})
 * is bound and validated here too, so a typo or an impossible value fails at startup, not at the
 * first wake-up. {@code handler-deadline} is optional: absent means nine tenths of the lease.
 */
@ConfigurationProperties("owlmast.jobs")
public record JobsProperties(
    Integer maxAttempts,
    Duration backoffBase,
    Duration backoffCap,
    Duration leaseDuration,
    Integer claimBatchSize,
    Duration pollInterval,
    Duration initialDelay,
    Duration handlerDeadline) {

  public JobsProperties {
    maxAttempts = orDefault(maxAttempts, WorkItemContract.DEFAULT_MAX_ATTEMPTS);
    backoffBase = orDefault(backoffBase, WorkItemContract.DEFAULT_BACKOFF_BASE);
    backoffCap = orDefault(backoffCap, WorkItemContract.DEFAULT_BACKOFF_CAP);
    leaseDuration = orDefault(leaseDuration, WorkItemContract.DEFAULT_LEASE_DURATION);
    claimBatchSize = orDefault(claimBatchSize, WorkItemContract.DEFAULT_CLAIM_BATCH_SIZE);
    pollInterval = orDefault(pollInterval, WorkItemContract.DEFAULT_POLL_INTERVAL);
    initialDelay = orDefault(initialDelay, WorkItemContract.DEFAULT_INITIAL_DELAY);
    if (pollInterval.isZero() || pollInterval.isNegative()) {
      throw new IllegalArgumentException("owlmast.jobs.poll-interval must be positive");
    }
    if (initialDelay.isNegative()) {
      throw new IllegalArgumentException("owlmast.jobs.initial-delay must not be negative");
    }
    // Builds the policy once so an impossible handler deadline is rejected at binding time.
    policyFor(maxAttempts, backoffBase, backoffCap, leaseDuration, claimBatchSize, handlerDeadline);
  }

  public RetryPolicy policy() {
    return policyFor(
        maxAttempts, backoffBase, backoffCap, leaseDuration, claimBatchSize, handlerDeadline);
  }

  private static RetryPolicy policyFor(
      int maxAttempts,
      Duration backoffBase,
      Duration backoffCap,
      Duration leaseDuration,
      int claimBatchSize,
      Duration handlerDeadline) {
    if (handlerDeadline == null) {
      return new RetryPolicy(maxAttempts, backoffBase, backoffCap, leaseDuration, claimBatchSize);
    }
    try {
      return new RetryPolicy(
          maxAttempts, backoffBase, backoffCap, leaseDuration, claimBatchSize, handlerDeadline);
    } catch (IllegalArgumentException invalid) {
      throw new IllegalArgumentException(
          "owlmast.jobs.handler-deadline: " + invalid.getMessage(), invalid);
    }
  }

  private static <T> T orDefault(T value, T fallback) {
    return Optional.ofNullable(value).orElse(fallback);
  }
}
