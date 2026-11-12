package com.aisquad.owlmast.platform.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.blocking.BoundedBlocking;
import com.aisquad.owlmast.platform.blocking.BoundedBlockingProperties;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

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

  /**
   * PR #119 walkthrough, risk 6: the catch-all must not turn a failure that carries its own status
   * into a 500. Each of these reaches {@code UnhandledFailureAdvice} (the framework's handler does
   * not know them) and keeps its status, as a problem detail without any of the exception.
   */
  @ParameterizedTest
  @CsvSource({
    "/api/test-only/failure/error-response, 422, Unprocessable Content",
    "/api/test-only/failure/error-response-signalled, 422, Unprocessable Content",
    "/api/test-only/failure/response-status, 410, Gone",
    "/api/test-only/failure/response-status-inherited, 410, Gone",
    "/api/test-only/failure/access-denied, 403, Forbidden",
    "/api/test-only/failure/access-denied-subclass, 403, Forbidden",
    "/api/test-only/failure/unauthenticated, 401, Unauthorized",
    "/api/test-only/failure/unauthenticated-signalled, 401, Unauthorized",
    // E01-R-05: the platform's own denial carries no web type and used to answer 500.
    "/api/test-only/failure/operation-denied, 403, Forbidden"
  })
  void aFailureThatCarriesItsOwnStatusKeepsIt(
      String path, int status, String title, CapturedOutput output) {
    byte[] body =
        client()
            .get()
            .uri(path)
            .exchange()
            .expectStatus()
            .isEqualTo(status)
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.status")
            .isEqualTo(status)
            .jsonPath("$.title")
            .isEqualTo(title)
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
        .doesNotContain("Exception");
    // An expected refusal is not an unhandled failure: no error line, and never the message.
    assertThat(output.getAll())
        .doesNotContain("Unhandled request failure")
        .doesNotContain("s3cr3t")
        .doesNotContain("\tat ");
  }

  @Test
  void anErrorResponseKeepsItsHeaders() {
    client()
        .get()
        .uri("/api/test-only/failure/error-response")
        .exchange()
        .expectStatus()
        .isEqualTo(422)
        .expectHeader()
        .valueEquals("Retry-After", "30");
  }

  @Test
  void aCarriedStatusThatIsNoErrorAnswersAs500() {
    client()
        .get()
        .uri("/api/test-only/failure/error-response-not-an-error")
        .exchange()
        .expectStatus()
        .isEqualTo(500)
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
        .expectHeader()
        .doesNotExist("Retry-After")
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo(500);
  }

  @ParameterizedTest
  @CsvSource({
    "/api/test-only/failure/error-response-unavailable, 503, Service Unavailable, OwnStatus",
    "/api/test-only/failure/identity-provider-down, 500, Internal Server Error,"
        + " IdentityProviderDown",
    // E01-R-05: the shared kernel's scope and bounded-blocking failures, raised by the real code.
    "/api/test-only/failure/missing-scope, 500, Internal Server Error, MissingScopeException",
    "/api/test-only/failure/blocking-capacity, 503, Service Unavailable,"
        + " BlockingCapacityExceededException",
    "/api/test-only/failure/blocking-deadline, 504, Gateway Timeout,"
        + " BlockingDeadlineExceededException"
  })
  void aCarriedServerErrorKeepsItsStatusAndIsLoggedAsAFailure(
      String path, int status, String title, String logged, CapturedOutput output) {
    client()
        .get()
        .uri(path)
        .exchange()
        .expectStatus()
        .isEqualTo(status)
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
        .expectBody()
        .jsonPath("$.status")
        .isEqualTo(status)
        .jsonPath("$.title")
        .isEqualTo(title)
        .jsonPath("$.detail")
        .doesNotExist();
    assertThat(output.getAll())
        .contains("Unhandled request failure: " + logged)
        .doesNotContain("s3cr3t")
        .doesNotContain("\tat ");
  }

  @Test
  void aCarriedServerErrorKeepsItsHeaders() {
    client()
        .get()
        .uri("/api/test-only/failure/error-response-unavailable")
        .exchange()
        .expectStatus()
        .isEqualTo(503)
        .expectHeader()
        .valueEquals("Retry-After", "30");
  }

  /**
   * The stand-ins under {@code src/integrationTest/java/org/springframework/security} exist only
   * while Spring Security is not a dependency. Once it is, the same class name resolves twice and
   * the stand-in could shadow the real class without anyone noticing: this fails instead.
   */
  @ParameterizedTest
  @ValueSource(
      classes = {
        AccessDeniedException.class,
        AuthenticationException.class,
        AuthenticationServiceException.class
      })
  void theSecurityStandInsAreTheOnlyClassesOfTheirName(Class<?> standIn) throws Exception {
    String resource = standIn.getName().replace('.', '/') + ".class";
    assertThat(java.util.Collections.list(getClass().getClassLoader().getResources(resource)))
        .hasSize(1)
        .allSatisfy(url -> assertThat(url.getProtocol()).isEqualTo("file"));
  }

  @Test
  void theStatusIsReadFromTheFailureItselfNotFromItsCause() {
    assertThat(UnhandledFailureAdvice.statusOf(new Denied(SECRET)).value()).isEqualTo(403);
    assertThat(UnhandledFailureAdvice.statusOf(new Unauthenticated(SECRET)).value()).isEqualTo(401);
    assertThat(
            UnhandledFailureAdvice.statusOf(new IllegalStateException(new Denied(SECRET))).value())
        .isEqualTo(500);
    assertThat(UnhandledFailureAdvice.statusOf(new SecurityException(SECRET)).value())
        .isEqualTo(500);
    // The order of the three sources: an ErrorResponse before an annotation before a name.
    assertThat(UnhandledFailureAdvice.statusOf(new DeniedButGone(SECRET)).value()).isEqualTo(410);
    // The nearest listed class wins: a failing identity provider is not a credential problem.
    assertThat(UnhandledFailureAdvice.statusOf(new AuthenticationServiceException(SECRET)).value())
        .isEqualTo(500);
    assertThat(UnhandledFailureAdvice.statusOf(new IdentityProviderDown(SECRET)).value())
        .isEqualTo(500);
    assertThat(UnhandledFailureAdvice.STATUS_BY_CLASS_NAME)
        .containsOnlyKeys(
            AccessDeniedException.class.getName(),
            AuthenticationException.class.getName(),
            AuthenticationServiceException.class.getName());
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

    @GetMapping("/api/test-only/failure/error-response")
    Mono<String> errorResponse() {
      throw new OwnStatus(HttpStatus.UNPROCESSABLE_CONTENT);
    }

    @GetMapping("/api/test-only/failure/error-response-signalled")
    Mono<String> errorResponseSignalled() {
      return Mono.error(new OwnStatus(HttpStatus.UNPROCESSABLE_CONTENT));
    }

    @GetMapping("/api/test-only/failure/error-response-not-an-error")
    Mono<String> errorResponseNotAnError() {
      throw new OwnStatus(HttpStatus.NO_CONTENT);
    }

    @GetMapping("/api/test-only/failure/error-response-unavailable")
    Mono<String> errorResponseUnavailable() {
      throw new OwnStatus(HttpStatus.SERVICE_UNAVAILABLE);
    }

    @GetMapping("/api/test-only/failure/identity-provider-down")
    Mono<String> identityProviderDown() {
      return Mono.error(new IdentityProviderDown(SECRET));
    }

    @GetMapping("/api/test-only/failure/response-status")
    Mono<String> responseStatus() {
      throw new GoneForGood(SECRET);
    }

    @GetMapping("/api/test-only/failure/response-status-inherited")
    Mono<String> responseStatusInherited() {
      return Mono.error(new GoneForGoodChild(SECRET));
    }

    @GetMapping("/api/test-only/failure/operation-denied")
    Mono<String> operationDenied() {
      return Mono.error(new OperationDeniedException("not-permitted"));
    }

    @GetMapping("/api/test-only/failure/missing-scope")
    Mono<String> missingScope() {
      return Scopes.current().map(scope -> scope.tenant().value());
    }

    /** One thread and one queued call are taken, so the third call is refused. */
    @GetMapping("/api/test-only/failure/blocking-capacity")
    Mono<String> blockingCapacity() {
      BoundedBlocking blocking =
          BoundedBlocking.create(new BoundedBlockingProperties(1, 1, Duration.ofSeconds(5)));
      CountDownLatch occupied = new CountDownLatch(1);
      CountDownLatch release = new CountDownLatch(1);
      Disposable first =
          blocking
              .call(
                  "occupying",
                  () -> {
                    occupied.countDown();
                    return release.await(5, TimeUnit.SECONDS);
                  })
              .subscribe();
      return Mono.fromCallable(() -> occupied.await(5, TimeUnit.SECONDS))
          .subscribeOn(Schedulers.boundedElastic())
          .flatMap(taken -> {
            Disposable queued = blocking.call("queued", () -> SECRET).subscribe();
            return blocking
                .call(SECRET, () -> "never")
                .doFinally(ended -> {
                  release.countDown();
                  queued.dispose();
                  first.dispose();
                  blocking.close();
                });
          });
    }

    @GetMapping("/api/test-only/failure/blocking-deadline")
    Mono<String> blockingDeadline() {
      BoundedBlocking blocking =
          BoundedBlocking.create(new BoundedBlockingProperties(1, 1, Duration.ofSeconds(5)));
      return blocking
          .call(
              SECRET,
              Duration.ofMillis(50),
              () -> {
                // The deadline cancels the call and interrupts this thread. Returning normally
                // keeps the test about the answer: an exception thrown after the cancellation has
                // no subscriber left and Reactor logs it with its stack trace (onErrorDropped).
                try {
                  Thread.sleep(2_000);
                } catch (InterruptedException cancelled) {
                  Thread.currentThread().interrupt();
                }
                return "late";
              })
          .doFinally(ended -> blocking.close());
    }

    @GetMapping("/api/test-only/failure/access-denied")
    Mono<String> accessDenied() {
      throw new AccessDeniedException(SECRET);
    }

    @GetMapping("/api/test-only/failure/access-denied-subclass")
    Mono<String> accessDeniedSubclass() {
      return Mono.error(new Denied(SECRET));
    }

    @GetMapping("/api/test-only/failure/unauthenticated")
    Mono<String> unauthenticated() {
      throw new Unauthenticated(SECRET);
    }

    @GetMapping("/api/test-only/failure/unauthenticated-signalled")
    Mono<String> unauthenticatedSignalled() {
      return Mono.error(new Unauthenticated(SECRET));
    }
  }

  /** An {@code ErrorResponse} the framework's handler does not know (neither of its base types). */
  static class OwnStatus extends RuntimeException implements ErrorResponse {

    private static final long serialVersionUID = 1L;

    private final HttpStatus status;

    OwnStatus(HttpStatus status) {
      super(SECRET);
      this.status = status;
    }

    @Override
    public HttpStatusCode getStatusCode() {
      return status;
    }

    @Override
    public HttpHeaders getHeaders() {
      HttpHeaders headers = new HttpHeaders();
      headers.set("Retry-After", "30");
      return headers;
    }

    @Override
    public ProblemDetail getBody() {
      return ProblemDetail.forStatusAndDetail(status, SECRET);
    }
  }

  @ResponseStatus(code = HttpStatus.GONE, reason = SECRET)
  static class GoneForGood extends RuntimeException {

    private static final long serialVersionUID = 1L;

    GoneForGood(String message) {
      super(message);
    }
  }

  static class GoneForGoodChild extends GoneForGood {

    private static final long serialVersionUID = 1L;

    GoneForGoodChild(String message) {
      super(message);
    }
  }

  static class Denied extends AccessDeniedException {

    private static final long serialVersionUID = 1L;

    Denied(String message) {
      super(message);
    }
  }

  @ResponseStatus(HttpStatus.GONE)
  static class DeniedButGone extends AccessDeniedException {

    private static final long serialVersionUID = 1L;

    DeniedButGone(String message) {
      super(message);
    }
  }

  static class IdentityProviderDown extends AuthenticationServiceException {

    private static final long serialVersionUID = 1L;

    IdentityProviderDown(String message) {
      super(message);
    }
  }

  static class Unauthenticated extends AuthenticationException {

    private static final long serialVersionUID = 1L;

    Unauthenticated(String message) {
      super(message);
    }
  }
}
