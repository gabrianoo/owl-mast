package com.aisquad.owlmast.access;

import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityProvider;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

/**
 * AC2: the application reaches readiness only with the identity provider it was configured for. A
 * provider that publishes another issuer keeps readiness DOWN while liveness stays UP.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import(ContainersConfiguration.class)
class IdentityReadinessIT {

  private static final StubIdentityProvider MISMATCHED =
      StubIdentityProvider.start("owl-mast", "https://someone-else.example/realms/owl-mast");

  @LocalServerPort private int port;

  @DynamicPropertySource
  static void issuer(DynamicPropertyRegistry registry) {
    registry.add("owlmast.identity.issuer-uri", MISMATCHED::issuerUri);
    registry.add("owlmast.identity.allow-insecure-issuer", () -> "true");
  }

  @AfterAll
  static void stop() {
    MISMATCHED.close();
  }

  @Test
  void readinessIsDownWithMismatchedIssuerWhileLivenessStaysUp() {
    WebTestClient client = WebTestClient.bindToServer().baseUrl("http://localhost:" + port).build();
    client
        .get()
        .uri("/actuator/health/readiness")
        .exchange()
        .expectStatus()
        .isEqualTo(503)
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo("DOWN");
    client
        .get()
        .uri("/actuator/health/liveness")
        .exchange()
        .expectStatus()
        .isOk()
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo("UP");
  }
}
