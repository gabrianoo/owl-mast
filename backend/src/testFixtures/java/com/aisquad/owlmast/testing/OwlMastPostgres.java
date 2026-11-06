package com.aisquad.owlmast.testing;

import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/** Factory for disposable PostgreSQL containers used by the integration suite. */
public final class OwlMastPostgres {

  private OwlMastPostgres() {}

  /** The qualified VectorChord image; the caller (or Spring) owns start/stop. */
  public static PostgreSQLContainer vectorChord() {
    return container(OwlMastImages.VECTORCHORD_POSTGRES);
  }

  /** A plain PostgreSQL image for negative extension tests only. */
  public static PostgreSQLContainer plainPostgres() {
    return container(OwlMastImages.PLAIN_POSTGRES);
  }

  /**
   * The image's default command preloads VectorChord ({@code postgres -c
   * shared_preload_libraries=vchord,vector}); Testcontainers replaces the command, so the preload
   * must be restated or {@code CREATE EXTENSION vchord} fails with "must be loaded via
   * shared_preload_libraries".
   */
  static final String[] VECTORCHORD_COMMAND = {
    "postgres", "-c", "shared_preload_libraries=vchord,vector", "-c", "fsync=off"
  };

  private static PostgreSQLContainer container(DockerImageName image) {
    ContainerRuntime.requireAvailable();
    PostgreSQLContainer container = new PostgreSQLContainer(image);
    if (image.equals(OwlMastImages.VECTORCHORD_POSTGRES)) {
      container.setCommand(VECTORCHORD_COMMAND);
    }
    return container
        .withDatabaseName("owlmast")
        .withUsername("owlmast")
        .withPassword("owlmast-integration-test");
  }
}
