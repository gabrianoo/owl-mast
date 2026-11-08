package com.aisquad.owlmast.jobs.domain;

import com.aisquad.owlmast.jobs.api.WorkItemContract;
import java.time.Duration;
import java.util.Objects;

/**
 * Bounded retry, lease and claim policy (AD-6). Backoff doubles per attempt from {@code
 * backoffBase} and is capped at {@code backoffCap}; the item is terminal once {@code maxAttempts}
 * have been used. A handler still running at {@code handlerDeadline} is cancelled; it defaults to
 * nine tenths of the lease, so the failed attempt is still written under the lease that claimed it
 * and the item is retried with backoff.
 */
public record RetryPolicy(
    int maxAttempts,
    Duration backoffBase,
    Duration backoffCap,
    Duration leaseDuration,
    int claimBatchSize,
    Duration handlerDeadline) {

  public static final RetryPolicy DEFAULTS =
      new RetryPolicy(
          WorkItemContract.DEFAULT_MAX_ATTEMPTS,
          WorkItemContract.DEFAULT_BACKOFF_BASE,
          WorkItemContract.DEFAULT_BACKOFF_CAP,
          WorkItemContract.DEFAULT_LEASE_DURATION,
          WorkItemContract.DEFAULT_CLAIM_BATCH_SIZE);

  public RetryPolicy {
    requirePositive(maxAttempts, "max attempts");
    requirePositive(claimBatchSize, "claim batch size");
    requirePositive(backoffBase, "backoff base");
    requirePositive(backoffCap, "backoff cap");
    requirePositive(leaseDuration, "lease duration");
    requirePositive(handlerDeadline, "handler deadline");
    if (handlerDeadline.compareTo(leaseDuration) >= 0) {
      throw new IllegalArgumentException(
          "handler deadline must be shorter than the lease, so the failed attempt is written under"
              + " the lease that claimed it");
    }
    if (backoffCap.compareTo(backoffBase) < 0) {
      throw new IllegalArgumentException("backoff cap must not be shorter than the backoff base");
    }
  }

  /** The default policy shape: the handler deadline is nine tenths of the lease. */
  public RetryPolicy(
      int maxAttempts,
      Duration backoffBase,
      Duration backoffCap,
      Duration leaseDuration,
      int claimBatchSize) {
    this(
        maxAttempts,
        backoffBase,
        backoffCap,
        leaseDuration,
        claimBatchSize,
        Objects.requireNonNull(leaseDuration, "lease duration").minus(leaseDuration.dividedBy(10)));
  }

  /**
   * Server-side bound for every statement in a handler's transaction: halfway between the handler
   * deadline and the lease expiry. A handler blocked inside the database (a lock wait, a slow
   * query) is cancelled by PostgreSQL in time for the rollback and the failure write to finish
   * under the lease; cancelling the reactive subscription alone would leave the rollback queued
   * behind it.
   */
  public Duration statementTimeout() {
    return handlerDeadline.plus(leaseDuration.minus(handlerDeadline).dividedBy(2));
  }

  /** Delay before the next attempt after {@code failedAttempt} (1-based) failed. */
  public Duration backoffFor(int failedAttempt) {
    if (failedAttempt < 1) {
      throw new IllegalArgumentException("attempt numbers start at 1");
    }
    int doublings = Math.min(failedAttempt - 1, 30);
    Duration candidate = backoffBase.multipliedBy(1L << doublings);
    return candidate.compareTo(backoffCap) > 0 ? backoffCap : candidate;
  }

  public boolean exhausted(int attemptsUsed) {
    return attemptsUsed >= maxAttempts;
  }

  private static void requirePositive(int value, String name) {
    if (value < 1) {
      throw new IllegalArgumentException(name + " must be at least 1");
    }
  }

  private static void requirePositive(Duration value, String name) {
    Objects.requireNonNull(value, name);
    if (value.isZero() || value.isNegative()) {
      throw new IllegalArgumentException(name + " must be positive");
    }
  }
}
