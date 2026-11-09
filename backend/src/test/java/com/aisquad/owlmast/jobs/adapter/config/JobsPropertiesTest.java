package com.aisquad.owlmast.jobs.adapter.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class JobsPropertiesTest {

  @Test
  void absentValuesFallBackToTheContractDefaults() {
    JobsProperties properties = new JobsProperties(null, null, null, null, null, null, null, null);

    assertThat(properties.policy()).isEqualTo(RetryPolicy.DEFAULTS);
    assertThat(properties.pollInterval()).isEqualTo(Duration.ofSeconds(1));
    assertThat(properties.initialDelay()).isEqualTo(Duration.ZERO);
    assertThat(properties.handlerDeadline()).as("absent: nine tenths of the lease").isNull();
  }

  @Test
  void explicitValuesWinAndInvalidOnesAreRejected() {
    JobsProperties properties =
        new JobsProperties(
            3,
            Duration.ofMillis(100),
            Duration.ofMillis(400),
            Duration.ofSeconds(5),
            2,
            Duration.ofMillis(200),
            null,
            null);

    assertThat(properties.policy().maxAttempts()).isEqualTo(3);
    assertThat(properties.policy().backoffFor(3)).isEqualTo(Duration.ofMillis(400));
    assertThatThrownBy(
            () -> new JobsProperties(null, null, null, null, null, Duration.ZERO, null, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("poll-interval");
  }

  @Test
  void schedulerDelaysAndTheHandlerDeadlineAreValidatedAtBindingTime() {
    JobsProperties properties =
        new JobsProperties(
            null,
            null,
            null,
            Duration.ofSeconds(20),
            null,
            null,
            Duration.ofSeconds(3),
            Duration.ofSeconds(12));

    assertThat(properties.initialDelay()).isEqualTo(Duration.ofSeconds(3));
    assertThat(properties.policy().handlerDeadline())
        .as("an explicit deadline replaces the nine-tenths default")
        .isEqualTo(Duration.ofSeconds(12));
    assertThat(properties.policy().leaseDuration()).isEqualTo(Duration.ofSeconds(20));
    assertThatThrownBy(() ->
            new JobsProperties(null, null, null, null, null, null, Duration.ofSeconds(-1), null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("initial-delay");
    assertThatThrownBy(() ->
            new JobsProperties(
                null, null, null, Duration.ofSeconds(20), null, null, null, Duration.ofSeconds(20)))
        .as("a deadline at or past the lease would write the failure outside the lease")
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("handler-deadline");
  }
}
