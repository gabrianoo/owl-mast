package com.aisquad.owlmast.jobs.adapter.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class JobsPropertiesTest {

  @Test
  void absentValuesFallBackToTheContractDefaults() {
    JobsProperties properties = new JobsProperties(null, null, null, null, null, null);

    assertThat(properties.policy()).isEqualTo(RetryPolicy.DEFAULTS);
    assertThat(properties.pollInterval()).isEqualTo(Duration.ofSeconds(1));
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
            Duration.ofMillis(200));

    assertThat(properties.policy().maxAttempts()).isEqualTo(3);
    assertThat(properties.policy().backoffFor(3)).isEqualTo(Duration.ofMillis(400));
    assertThatThrownBy(() -> new JobsProperties(null, null, null, null, null, Duration.ZERO))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("poll-interval");
  }
}
