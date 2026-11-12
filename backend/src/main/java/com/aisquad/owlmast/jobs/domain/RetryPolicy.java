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
   * Server-side end of a handler's transaction, counted from the claim like the handler deadline:
   * halfway between the handler deadline and the lease expiry. PostgreSQL ends the transaction (and
   * its session) at that moment whatever it is doing and whenever its current statement started, so
   * a handler blocked inside the database (a lock wait, a slow query) is stopped in time for the
   * failure write to finish under the lease; cancelling the reactive subscription alone would leave
   * the rollback queued behind the statement. What is guaranteed is the moment the server stops
   * working for the handler; the failure write still needs the database to answer within the other
   * half of the margin.
   */
  public Duration handlerCutoff() {
    return handlerDeadline.plus(leaseDuration.minus(handlerDeadline).dividedBy(2));
  }

  /**
   * The share of the handler deadline the authorization recheck may use, counted from the claim:
   * half of it. A recheck that has not allowed the dispatch by then counts as undecided and the
   * item is released uncounted, so a slow deciding component can never leave the handler a budget
   * too short to finish and have that charged to the item as a failed attempt.
   */
  public Duration recheckDeadline() {
    return handlerDeadline.dividedBy(2);
  }

  /**
   * Bound of every processor step outside the handler (tenant discovery, the exhausted-lease sweep,
   * the claim, and the release, deny and failure writes): one lease. Past it the lease the step
   * works under has run out anyway, so a statement stalled by the database or the network fails the
   * step instead of stopping every later wake-up.
   */
  public Duration stepTimeout() {
    return leaseDuration;
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
