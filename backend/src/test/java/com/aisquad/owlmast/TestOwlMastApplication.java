package com.aisquad.owlmast;

import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.SyntheticKeycloakConfiguration;
import org.springframework.boot.SpringApplication;

/**
 * Local run against a disposable VectorChord container and the pinned Keycloak with a synthetic
 * realm: {@code ./gradlew :backend:bootTestRun}. Sign-in works end to end; the synthetic users
 * ({@code ada.synthetic}, {@code grace.synthetic}) take their password from the environment
 * variable {@code OWLMAST_FIXTURE_USER_PASSWORD}. Pass the address the browser uses for the shell
 * as {@code --owlmast.sign-in.application-origin=...} (default {@code http://localhost:8080}).
 */
public final class TestOwlMastApplication {

  private TestOwlMastApplication() {}

  public static void main(String[] args) {
    SpringApplication.from(OwlMastApplication::main)
        .with(ContainersConfiguration.class, SyntheticKeycloakConfiguration.class)
        .run(args);
  }
}
