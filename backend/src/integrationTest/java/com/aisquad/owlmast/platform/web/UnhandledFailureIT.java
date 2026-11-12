package com.aisquad.owlmast.platform.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

/**
 * OM-01.04 common error envelope: a failure nobody handled answers as an RFC 9457 problem detail
 * with status 500 and none of the exception, and the framework's own error responses keep their
 * status. The failing endpoints exist only in this test.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({
  ContainersConfiguration.class,
  StubIdentityConfiguration.class,
  UnhandledFailureIT.FailingController.class
})
@ExtendWith(OutputCaptureExtension.class)
class UnhandledFailureIT {

  private static final String SECRET = "r2dbc:postgresql://owlmast:s3cr3t@db.internal:5432/owlmast";

  @LocalServerPort private int port;

  @ParameterizedTest
  @ValueSource(strings = {"/api/test-only/failure/thrown", "/api/test-only/failure/signalled"})
  void anUnhandledFailureIsAProblemDetailWithoutInternals(String path, CapturedOutput output) {
    byte[] body =
        client()
            .get()
            .uri(path)
            .exchange()
            .expectStatus()
            .isEqualTo(500)
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status")
            .isEqualTo(500)
            .jsonPath("$.title")
            .isEqualTo("Internal Server Error")
            .jsonPath("$.instance")
            .isEqualTo(path)
            .jsonPath("$.detail")
            .doesNotExist()
            .jsonPath("$.trace")
            .doesNotExist()
            .jsonPath("$.message")
            .doesNotExist()
            .jsonPath("$.exception")
            .doesNotExist()
            .jsonPath("$.error")
            .doesNotExist()
            .returnResult()
            .getResponseBody();
    assertThat(new String(body, StandardCharsets.UTF_8))
        .doesNotContain("s3cr3t")
        .doesNotContain("db.internal")
        .doesNotContain("IllegalStateException");
    // The log names the exception classes and nothing the exception carried (message, cause,
    // trace).
    assertThat(output.getAll())
        .contains("Unhandled request failure: IllegalStateException")
        .doesNotContain("s3cr3t")
        .doesNotContain("db.internal")
        .doesNotContain("\tat ");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {"/api/test-only/failure/error-thrown", "/api/test-only/failure/error-signalled"})
  void anErrorIsAnsweredWithTheSameEnvelope(String path, CapturedOutput output) {
    byte[] body =
        client()
            .get()
            .uri(path)
            .exchange()
            .expectStatus()
            .isEqualTo(500)
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status")
            .isEqualTo(500)
            .jsonPath("$.title")
            .isEqualTo("Internal Server Error")
            .jsonPath("$.detail")
            .doesNotExist()
            .jsonPath("$.trace")
            .doesNotExist()
            .jsonPath("$.message")
            .doesNotExist()
            .jsonPath("$.exception")
            .doesNotExist()
            .jsonPath("$.error")
            .doesNotExist()
            .returnResult()
            .getResponseBody();
    assertThat(new String(body, StandardCharsets.UTF_8))
        .doesNotContain("s3cr3t")
        .doesNotContain("AssertionError");
    assertThat(output.getAll())
        .contains("Unhandled request failure: AssertionError")
        .doesNotContain("s3cr3t")
        .doesNotContain("\tat ");
  }

  @Test
  void theFrameworksOwnErrorResponsesKeepTheirStatus() {
    client()
        .get()
        .uri("/api/test-only/failure/status")
        .exchange()
        .expectStatus()
        .isEqualTo(409)
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo(409);
    client()
        .post()
        .uri("/api/test-only/failure/thrown")
        .exchange()
        .expectStatus()
        .isEqualTo(405)
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON);
  }

  private WebTestClient client() {
    return WebTestClient.bindToServer().baseUrl("http://localhost:" + port).build();
  }

  @RestController
  static class FailingController {

    @GetMapping("/api/test-only/failure/thrown")
    Mono<String> thrown() {
      throw new IllegalStateException(SECRET);
    }

    @GetMapping("/api/test-only/failure/signalled")
    Mono<String> signalled() {
      return Mono.error(new IllegalStateException(SECRET, new RuntimeException(SECRET)));
    }

    @GetMapping("/api/test-only/failure/error-thrown")
    Mono<String> errorThrown() {
      throw new AssertionError(SECRET);
    }

    @GetMapping("/api/test-only/failure/error-signalled")
    Mono<String> errorSignalled() {
      return Mono.error(new AssertionError(SECRET));
    }

    @GetMapping("/api/test-only/failure/status")
    Mono<String> status() {
      return Mono.error(new ResponseStatusException(org.springframework.http.HttpStatus.CONFLICT));
    }
  }
}
