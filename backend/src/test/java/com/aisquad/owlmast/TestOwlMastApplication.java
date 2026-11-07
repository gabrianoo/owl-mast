package com.aisquad.owlmast;

import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import org.springframework.boot.SpringApplication;

/** Local run against a disposable VectorChord container: {@code ./gradlew :backend:bootTestRun}. */
public final class TestOwlMastApplication {

  private TestOwlMastApplication() {}

  public static void main(String[] args) {
    SpringApplication.from(OwlMastApplication::main)
        .with(ContainersConfiguration.class, StubIdentityConfiguration.class)
        .run(args);
  }
}
