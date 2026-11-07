package com.aisquad.owlmast;

import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

/** AC1: the application starts against the real database and the health endpoint answers UP. */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({ContainersConfiguration.class, StubIdentityConfiguration.class})
class HealthEndpointIT {

  @LocalServerPort private int port;

  @Test
  void healthIsUpWithoutExposingComponentDetails() {
    client()
        .get()
        .uri("/actuator/health")
        .exchange()
        .expectStatus()
        .isOk()
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo("UP")
        .jsonPath("$.components")
        .doesNotExist();
  }

  @Test
  void readinessProbeIsExposed() {
    client()
        .get()
        .uri("/actuator/health/readiness")
        .exchange()
        .expectStatus()
        .isOk()
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo("UP");
  }

  private WebTestClient client() {
    return WebTestClient.bindToServer().baseUrl("http://localhost:" + port).build();
  }
}
