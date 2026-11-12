package com.aisquad.owlmast.jobs.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.jobs.api.WorkItemContract;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** AC5: capped exponential backoff and terminal attempts come from the contract defaults. */
class RetryPolicyTest {

  @Test
  void defaultsMatchTheContract() {
    assertThat(RetryPolicy.DEFAULTS.maxAttempts()).isEqualTo(WorkItemContract.DEFAULT_MAX_ATTEMPTS);
    assertThat(RetryPolicy.DEFAULTS.backoffBase()).isEqualTo(WorkItemContract.DEFAULT_BACKOFF_BASE);
    assertThat(RetryPolicy.DEFAULTS.backoffCap()).isEqualTo(WorkItemContract.DEFAULT_BACKOFF_CAP);
    assertThat(RetryPolicy.DEFAULTS.leaseDuration())
        .isEqualTo(WorkItemContract.DEFAULT_LEASE_DURATION);
    assertThat(RetryPolicy.DEFAULTS.claimBatchSize())
        .isEqualTo(WorkItemContract.DEFAULT_CLAIM_BATCH_SIZE);
  }

  @Test
  void backoffDoublesPerAttemptAndIsCapped() {
    RetryPolicy policy =
        new RetryPolicy(
            10, Duration.ofSeconds(1), Duration.ofSeconds(5), Duration.ofSeconds(30), 10);

    assertThat(policy.backoffFor(1)).isEqualTo(Duration.ofSeconds(1));
    assertThat(policy.backoffFor(2)).isEqualTo(Duration.ofSeconds(2));
    assertThat(policy.backoffFor(3)).isEqualTo(Duration.ofSeconds(4));
    assertThat(policy.backoffFor(4)).isEqualTo(Duration.ofSeconds(5));
    assertThat(policy.backoffFor(100))
        .as("no overflow far past the cap")
        .isEqualTo(Duration.ofSeconds(5));
  }

  @Test
  void exhaustionIsReachedAtMaxAttempts() {
    assertThat(RetryPolicy.DEFAULTS.exhausted(4)).isFalse();
    assertThat(RetryPolicy.DEFAULTS.exhausted(5)).isTrue();
  }

  @Test
  void rejectsNonPositiveValuesAndACapBelowTheBase() {
    assertThatThrownBy(() -> RetryPolicy.DEFAULTS.backoffFor(0))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() ->
            new RetryPolicy(
                0, Duration.ofSeconds(1), Duration.ofSeconds(5), Duration.ofSeconds(1), 1))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() ->
            new RetryPolicy(
                1, Duration.ofSeconds(5), Duration.ofSeconds(1), Duration.ofSeconds(1), 1))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("cap");
    assertThatThrownBy(() ->
            new RetryPolicy(1, Duration.ofSeconds(1), Duration.ofSeconds(1), Duration.ZERO, 1))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("lease");
  }

  @Test
  void handlersAreCancelledAtNineTenthsOfTheLeaseSoTheFailureIsWrittenUnderIt() {
    RetryPolicy policy =
        new RetryPolicy(3, Duration.ofSeconds(1), Duration.ofSeconds(5), Duration.ofSeconds(30), 1);

    assertThat(policy.handlerDeadline()).isEqualTo(Duration.ofSeconds(27));
    assertThat(RetryPolicy.DEFAULTS.handlerDeadline())
        .isLessThan(WorkItemContract.DEFAULT_LEASE_DURATION)
        .isPositive();
    assertThatThrownBy(() ->
            new RetryPolicy(
                3,
                Duration.ofSeconds(1),
                Duration.ofSeconds(5),
                Duration.ofSeconds(30),
                1,
                Duration.ZERO))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() ->
            new RetryPolicy(
                3,
                Duration.ofSeconds(1),
                Duration.ofSeconds(5),
                Duration.ofSeconds(30),
                1,
                Duration.ofSeconds(30)))
        .as("the deadline must leave the failure write inside the lease")
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(policy.statementTimeout())
        .as("server-side bound halfway between the deadline and the lease expiry")
        .isEqualTo(Duration.ofMillis(28_500));
  }

  @Test
  void theRecheckMayUseHalfTheHandlerDeadlineAndEveryOtherStepIsBoundedByTheLease() {
    RetryPolicy policy =
        new RetryPolicy(3, Duration.ofSeconds(1), Duration.ofSeconds(5), Duration.ofSeconds(30), 1);

    assertThat(policy.recheckDeadline())
        .as("the handler always keeps at least half of its deadline")
        .isEqualTo(Duration.ofMillis(13_500));
    assertThat(policy.stepTimeout()).isEqualTo(policy.leaseDuration());
  }
}
