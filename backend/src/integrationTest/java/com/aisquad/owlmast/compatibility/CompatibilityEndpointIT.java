package com.aisquad.owlmast.compatibility;

import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

/**
 * AC4: the backend publishes its API contract for the independently deployed frontend and the
 * pre-rollout check, without a credential. Since OM-02.01 every other API path needs an
 * authenticated principal, so an unknown path answers 401 to a caller without one, in the common
 * problem-details envelope and with the challenge (404 for a signed-in caller: SignInIT).
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({ContainersConfiguration.class, StubIdentityConfiguration.class})
class CompatibilityEndpointIT {

  @LocalServerPort private int port;

  /** The version the build stamped; asserting a literal would break this test on every bump. */
  @Autowired private BuildProperties buildProperties;

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
        .isEqualTo(buildProperties.getVersion())
        .jsonPath("$.apiContract.major")
        .isEqualTo(1)
        .jsonPath("$.apiContract.minor")
        .isEqualTo(1);
  }

  @Test
  void anUnknownApiPathNeedsACredentialAndAnswersInTheProblemDetailsEnvelope() {
    client()
        .get()
        .uri("/api/does-not-exist")
        .exchange()
        .expectStatus()
        .isUnauthorized()
        .expectHeader()
        .valueEquals("WWW-Authenticate", "Bearer")
        .expectHeader()
        .doesNotExist("Location")
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo(401)
        .jsonPath("$.title")
        .isEqualTo("Unauthorized")
        .jsonPath("$.instance")
        .isEqualTo("/api/does-not-exist")
        .jsonPath("$.detail")
        .doesNotExist()
        .jsonPath("$.trace")
        .doesNotExist()
        .jsonPath("$.exception")
        .doesNotExist();
  }

  private WebTestClient client() {
    return WebTestClient.bindToServer().baseUrl("http://localhost:" + port).build();
  }
}
