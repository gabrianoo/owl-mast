package com.aisquad.owlmast.compatibility;

import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

/**
 * AC4: the backend publishes its API contract for the independently deployed frontend and the
 * pre-rollout check; unknown API paths answer with the common problem-details envelope and no
 * internals.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({ContainersConfiguration.class, StubIdentityConfiguration.class})
class CompatibilityEndpointIT {

  @LocalServerPort private int port;

  @Test
  void publishesTheCompatibilityDescriptor() {
    client()
        .get()
        .uri("/api/compatibility")
        .exchange()
        .expectStatus()
        .isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.service")
        .isEqualTo("owl-mast-backend")
        .jsonPath("$.backendVersion")
        .isEqualTo("0.1.0-SNAPSHOT")
        .jsonPath("$.apiContract.major")
        .isEqualTo(1)
        .jsonPath("$.apiContract.minor")
        .isEqualTo(0);
  }

  @Test
  void unknownApiPathsUseTheProblemDetailsEnvelopeWithoutInternals() {
    client()
        .get()
        .uri("/api/does-not-exist")
        .exchange()
        .expectStatus()
        .isNotFound()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo(404)
        .jsonPath("$.title")
        .isEqualTo("Not Found")
        .jsonPath("$.trace")
        .doesNotExist()
        .jsonPath("$.exception")
        .doesNotExist();
  }

  private WebTestClient client() {
    return WebTestClient.bindToServer().baseUrl("http://localhost:" + port).build();
  }
}
