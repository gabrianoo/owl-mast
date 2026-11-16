package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.access.adapter.web.SessionFixture.Outcome;
import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import java.net.URI;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

/**
 * How a sign-in that did not complete ends, one case per kind of failure: where the browser is
 * sent, what is recorded, and what becomes of the session the sign-in was started in.
 */
class SignInOutcomeHandlersTest {

  private static final URI UNAVAILABLE = URI.create("https://owl.example/?sign-in=unavailable");
  private static final URI FAILED = URI.create("https://owl.example/?sign-in=failed");

  private final SessionFixture fixture = new SessionFixture();
  private final SignInOutcomeHandlers handlers =
      new SignInOutcomeHandlers(
          fixture.keeper,
          fixture.ledger,
          fixture.responses,
          new WebSessionServerCsrfTokenRepository());

  /** The session a sign-in was started in: it holds the pending authorization request. */
  private final WebSession pending = fixture.session();

  @AfterEach
  void stop() {
    fixture.close();
  }

  @ParameterizedTest
  @ValueSource(strings = {"server_error", "temporarily_unavailable", "invalid_token_response"})
  void aProviderFailureAtTheCallbackIsAnOutage(String errorCode) {
    MockServerWebExchange exchange = callback(true);

    fail(exchange, new OAuth2AuthenticationException(new OAuth2Error(errorCode)));

    assertReturnedTo(exchange, UNAVAILABLE);
    assertThat(fixture.outcomes)
        .containsExactly(
            new Outcome("session.sign-in", "FAILED", null, "OAuth2AuthenticationException"));
    assertThat(pending.isExpired()).isTrue();
  }

  /** The provider unreachable, keys that could not be fetched, the principal store failing. */
  @Test
  void aServiceFailureAtTheCallbackIsAnOutage() {
    MockServerWebExchange exchange = callback(true);

    fail(exchange, new AuthenticationServiceException("sign-in could not be completed"));

    assertReturnedTo(exchange, UNAVAILABLE);
    assertThat(fixture.outcomes)
        .containsExactly(
            new Outcome("session.sign-in", "FAILED", null, "AuthenticationServiceException"));
    assertThat(pending.isExpired()).isTrue();
    // Any other caller gets the status in the envelope.
    MockServerWebExchange api = callback(false);
    fail(api, new AuthenticationServiceException("sign-in could not be completed"));
    assertThat(api.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
  }

  @ParameterizedTest
  @CsvSource({
    "access_denied, sign-in-declined",
    "invalid_grant, authorization-code-rejected",
    "invalid_id_token, id-token-rejected",
    "invalid_nonce, id-token-rejected",
    "something_the_provider_made_up, sign-in-refused"
  })
  void aRefusalIsRecordedUnderItsFixedReasonAndLeavesNoSession(String errorCode, String reason) {
    MockServerWebExchange exchange = callback(true);

    fail(exchange, new OAuth2AuthenticationException(new OAuth2Error(errorCode)));

    assertReturnedTo(exchange, FAILED);
    assertThat(fixture.outcomes)
        .containsExactly(new Outcome("session.sign-in", "DENIED", null, reason));
    assertThat(pending.isExpired()).isTrue();
    MockServerWebExchange api = callback(false);
    fail(api, new OAuth2AuthenticationException(new OAuth2Error(errorCode)));
    assertThat(api.getResponse().getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    assertThat(api.getResponse().getHeaders().getFirst("WWW-Authenticate")).isEqualTo("Bearer");
  }

  /** Anyone can send a browser to the callback: a sign-in that is still pending survives it. */
  @ParameterizedTest
  @ValueSource(strings = {"authorization_request_not_found", "invalid_state_parameter"})
  void anAnswerThatMatchesNoStartedSignInLeavesThePendingOnesAlone(String errorCode) {
    MockServerWebExchange exchange = callback(true);

    fail(exchange, new OAuth2AuthenticationException(new OAuth2Error(errorCode)));

    assertReturnedTo(exchange, FAILED);
    assertThat(fixture.outcomes)
        .containsExactly(
            new Outcome("session.sign-in", "DENIED", null, "authorization-response-unmatched"));
    assertThat(pending.isExpired()).isFalse();
  }

  @Test
  void aFailedCallbackDoesNotEndASessionSomebodyIsSignedInWith() {
    pending
        .getAttributes()
        .put(
            WebSessionServerSecurityContextRepository.DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME,
            new SecurityContextImpl(SessionFixture.authentication(fixture.person("ref-1", "ada"))));
    MockServerWebExchange exchange = callback(true);

    fail(exchange, new OAuth2AuthenticationException(new OAuth2Error("access_denied")));

    assertReturnedTo(exchange, FAILED);
    assertThat(pending.isExpired()).isFalse();
  }

  @Test
  void anAuthenticationFailureRaisedElsewhereIsNotTheEndOfASignIn() {
    MockServerWebExchange exchange =
        fixture.exchange(MockServerHttpRequest.get("/api/anything"), pending);
    BadCredentialsException raised = new BadCredentialsException("from an operation");

    Throwable signalled =
        handlers
            .failure()
            .onAuthenticationFailure(
                new WebFilterExchange(exchange, ignored -> Mono.empty()), raised)
            .then(Mono.<Throwable>empty())
            .onErrorResume(Mono::just)
            .block(SessionFixture.CALL);

    assertThat(signalled).isSameAs(raised);
    assertThat(fixture.outcomes).isEmpty();
    assertThat(pending.isExpired()).isFalse();
  }

  /** A provider that cannot be reached, or a full session store, on either sign-in address. */
  @ParameterizedTest
  @ValueSource(strings = {SessionPaths.SIGN_IN, SessionPaths.CALLBACK})
  void anOutageOnASignInAddressEndsTheSignInLikeAnyOtherOutage(String path) {
    for (RuntimeException outage :
        new RuntimeException[] {
          new IdentityProviderUnavailableException(new IllegalStateException("down")),
          new SessionCapacityExceededException()
        }) {
      fixture.outcomes.clear();
      WebSession started = fixture.session();
      MockServerWebExchange exchange =
          fixture.exchange(MockServerHttpRequest.get(path).header("Accept", "text/html"), started);

      handlers
          .providerOutage()
          .filter(exchange, ignored -> Mono.error(outage))
          .block(SessionFixture.CALL);

      assertReturnedTo(exchange, UNAVAILABLE);
      assertThat(fixture.outcomes)
          .containsExactly(
              new Outcome("session.sign-in", "FAILED", null, outage.getClass().getSimpleName()));
      assertThat(started.isExpired()).isTrue();
    }
  }

  @Test
  void anOutageElsewhereAnswersTheStatusAndRecordsNoSignIn() {
    MockServerWebExchange exchange =
        fixture.exchange(
            MockServerHttpRequest.get("/api/anything").header("Accept", "text/html"), pending);

    handlers
        .providerOutage()
        .filter(
            exchange,
            ignored ->
                Mono.error(new IdentityProviderUnavailableException(new IllegalStateException())))
        .block(SessionFixture.CALL);

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    assertThat(exchange.getResponse().getHeaders().getLocation()).isNull();
    assertThat(fixture.outcomes).isEmpty();
    assertThat(pending.isExpired()).isFalse();
  }

  private MockServerWebExchange callback(boolean navigation) {
    MockServerHttpRequest.BaseBuilder<?> request =
        MockServerHttpRequest.get(SessionPaths.CALLBACK + "?code=synthetic&state=synthetic");
    return fixture.exchange(navigation ? request.header("Accept", "text/html") : request, pending);
  }

  private void fail(MockServerWebExchange exchange, AuthenticationException failure) {
    handlers
        .failure()
        .onAuthenticationFailure(new WebFilterExchange(exchange, ignored -> Mono.empty()), failure)
        .block(SessionFixture.CALL);
  }

  private static void assertReturnedTo(MockServerWebExchange exchange, URI shell) {
    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.SEE_OTHER);
    assertThat(exchange.getResponse().getHeaders().getLocation()).isEqualTo(shell);
  }
}
