package com.aisquad.owlmast.testing;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** The fixture must fail explicitly, never skip, when no container runtime is reachable (AC4). */
class ContainerRuntimeTest {

  @Test
  void unavailableRuntimeFailsWithAnExplicitMessage() {
    assertThatThrownBy(() -> ContainerRuntime.requireAvailable(() -> false))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("container runtime")
        .hasMessageContaining("fail rather than skip")
        .hasMessageContaining("docs/development.md");
  }

  @Test
  void availableRuntimePasses() {
    assertThatCode(() -> ContainerRuntime.requireAvailable(() -> true)).doesNotThrowAnyException();
  }
}
