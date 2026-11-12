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
 * AC2 (review R1): a reachable discovery endpoint that answers 204 with no body publishes no
 * issuer. The aggregate HTTP readiness must be 503 DOWN, not an UP assembled from the other
 * contributors, while liveness stays UP. The empty-200 variant is covered at the indicator level;
 * both share the same empty-body path.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import(ContainersConfiguration.class)
class IdentityEmptyDiscoveryIT {

  private static final StubIdentityProvider EMPTY =
      StubIdentityProvider.startEmpty("owl-mast", 204);

  @LocalServerPort private int port;

  @DynamicPropertySource
  static void issuer(DynamicPropertyRegistry registry) {
    registry.add("owlmast.identity.issuer-uri", EMPTY::issuerUri);
    registry.add("owlmast.identity.allow-insecure-issuer", () -> "true");
  }

  @AfterAll
  static void stop() {
    EMPTY.close();
  }

  @Test
  void aggregateReadinessIsDownOnAnEmptyDiscoveryResponse() {
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
