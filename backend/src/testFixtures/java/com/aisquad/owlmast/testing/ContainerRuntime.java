package com.aisquad.owlmast.testing;

import java.util.function.BooleanSupplier;
import org.testcontainers.DockerClientFactory;

/**
 * Integration tests need a Docker-compatible runtime. When none is reachable they fail with this
 * explicit message instead of being skipped (AC4).
 */
public final class ContainerRuntime {

  static final String UNAVAILABLE_MESSAGE =
      "Owl Mast integration tests require a reachable Docker-compatible container runtime"
          + " (Docker Engine/Desktop, or a DOCKER_HOST Testcontainers can use); none was found."
          + " Tests fail rather than skip. See docs/development.md#container-runtime";

  private ContainerRuntime() {}

  public static void requireAvailable() {
    requireAvailable(() -> DockerClientFactory.instance().isDockerAvailable());
  }

  static void requireAvailable(BooleanSupplier probe) {
    if (!probe.getAsBoolean()) {
      throw new IllegalStateException(UNAVAILABLE_MESSAGE);
    }
  }
}
