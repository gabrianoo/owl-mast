package com.aisquad.owlmast.bootstrap.adapter.health;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.Status;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

/** Component-level check of the bootstrap health contribution without a database. */
@ExtendWith(OutputCaptureExtension.class)
class SchemaBaselineHealthIndicatorTest {

  private static final SchemaBaseline BASELINE =
      new SchemaBaseline("1.1.1", "0.8.2", Instant.parse("2026-11-06T10:00:00Z"));

  @Test
  void reportsUpWithExtensionVersionsWhenBaselineExists() {
    StepVerifier.create(new SchemaBaselineHealthIndicator(() -> Mono.just(BASELINE)).health())
        .assertNext(health -> {
          assertThat(health.getStatus()).isEqualTo(Status.UP);
          assertThat(health.getDetails())
              .containsEntry("vchord", "1.1.1")
              .containsEntry("vector", "0.8.2")
              .containsEntry("appliedAt", "2026-11-06T10:00:00Z");
        })
        .verifyComplete();
  }

  @Test
  void reportsDownWhenBaselineIsMissing() {
    StepVerifier.create(new SchemaBaselineHealthIndicator(Mono::empty).health())
        .assertNext(health -> assertDown(health, "schema baseline not recorded"))
        .verifyComplete();
  }

  @Test
  void reportsDownWithoutLeakingTheFailureIntoTheResponseOrTheLogs(CapturedOutput output) {
    Mono<SchemaBaseline> failing =
        Mono.error(
            new IllegalStateException(
                "host=db password=OUTER_SECRET_MARKER",
                new java.io.IOException("token=NESTED_SECRET_MARKER")));

    StepVerifier.create(new SchemaBaselineHealthIndicator(() -> failing).health())
        .assertNext(health -> {
          assertDown(health, "schema baseline query failed");
          assertThat(health.getDetails().toString())
              .doesNotContain("OUTER_SECRET_MARKER", "NESTED_SECRET_MARKER");
        })
        .verifyComplete();

    assertThat(output)
        .as("the log line stays useful (class names) but carries no message or cause text")
        .contains("Schema baseline health check failed: IllegalStateException <- IOException")
        .doesNotContain("OUTER_SECRET_MARKER", "NESTED_SECRET_MARKER", "host=", "token=", "\tat ");
  }

  private static void assertDown(Health health, String reason) {
    assertThat(health.getStatus()).isEqualTo(Status.DOWN);
    assertThat(health.getDetails()).containsEntry("reason", reason);
  }
}
