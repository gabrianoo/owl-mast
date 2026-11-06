package com.aisquad.owlmast.platform.diagnostics;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class SafeFailureTest {

  @Test
  void describesOnlyClassNamesOfTheCauseChain() {
    Throwable failure =
        new IllegalStateException(
            "host=db password=OUTER_SECRET",
            new IOException("token=NESTED_SECRET", new RuntimeException("DEEP_SECRET")));

    String description = SafeFailure.describe(failure);

    assertThat(description)
        .isEqualTo("IllegalStateException <- IOException <- RuntimeException")
        .doesNotContain("SECRET", "host=", "token=");
  }

  @Test
  void boundsDepthAndTerminatesOnCycles() {
    RuntimeException root = new RuntimeException("r");
    Throwable deep = root;
    for (int i = 0; i < 10; i++) {
      deep = new IllegalArgumentException("level-" + i, deep);
    }
    assertThat(SafeFailure.describe(deep).split(" <- ")).hasSize(SafeFailure.MAX_DEPTH + 1);
    assertThat(SafeFailure.describe(deep)).endsWith("…").doesNotContain("level-");

    RuntimeException first = new RuntimeException("a");
    RuntimeException second = new RuntimeException("b", first);
    first.initCause(second);
    assertThat(SafeFailure.describe(first)).isEqualTo("RuntimeException <- RuntimeException");
    assertThat(SafeFailure.describe(null)).isEqualTo("unknown failure");
  }
}
