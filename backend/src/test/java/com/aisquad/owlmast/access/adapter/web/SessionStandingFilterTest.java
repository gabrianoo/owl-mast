package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.WebSession;

/**
 * What a request with a signed-in session gets, by the session's standing: served, served without
 * the session, or 503. The interesting row is the provider that cannot be asked: a protected call
 * is not served and not turned into "signed out", public content is still served, and sign-out
 * still reaches its handler with the session.
 */
class SessionStandingFilterTest {

  /** What the rest of the chain saw: null when it was not reached. */
  private enum Reached {
    WITH_SESSION,
    WITHOUT_SESSION
  }

  private final SessionFixture fixture = new SessionFixture();
  private final WebFilter filter =
      SessionWebFilters.standing(
          fixture.keeper,
          fixture.responses,
          new PathPatternParserServerWebExchangeMatcher("/api/compatibility", HttpMethod.GET),
          new PathPatternParserServerWebExchangeMatcher(SessionPaths.SIGN_OUT, HttpMethod.POST));
  private final WebSession session = fixture.session();
  private final OAuth2AuthenticationToken authentication =
      SessionFixture.authentication(fixture.person("ref-1", "ada"));

  SessionStandingFilterTest() {
    fixture
        .keeper
        .started(session, (SignedInPerson) authentication.getPrincipal())
        .block(SessionFixture.CALL);
  }

  @AfterEach
  void stop() {
    fixture.close();
  }

  @Test
  void aStandingSessionIsServedWithItsSession() {
    fixture.renewalSucceeds();

    MockServerWebExchange exchange = exchange(MockServerHttpRequest.get("/api/anything"));
    assertThat(run(exchange)).isEqualTo(Reached.WITH_SESSION);
  }

  @Test
  void whenTheProviderCannotBeAskedAProtectedCallIsNotServedAndTheSessionIsKept() {
    fixture.renewalFailsWith("server_error");

    MockServerWebExchange exchange = exchange(MockServerHttpRequest.get("/api/anything"));
    assertThat(run(exchange)).isNull();
    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    assertThat(exchange.getResponse().getHeaders().getContentType())
        .hasToString("application/problem+json");
    // A browser navigation gets the status too: this is not a sign-in step.
    MockServerWebExchange navigation =
        exchange(MockServerHttpRequest.get("/api/session").header("Accept", "text/html"));
    assertThat(run(navigation)).isNull();
    assertThat(navigation.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);

    assertThat(session.isExpired()).isFalse();
    assertThat(fixture.actions()).isEmpty();
  }

  @Test
  void whenTheProviderCannotBeAskedPublicContentIsServedWithoutTheSession() {
    fixture.renewalFailsWith("server_error");

    assertThat(run(exchange(MockServerHttpRequest.get("/api/compatibility"))))
        .isEqualTo(Reached.WITHOUT_SESSION);
    assertThat(session.isExpired()).isFalse();
    assertThat(fixture.actions()).isEmpty();
  }

  @Test
  void whenTheProviderCannotBeAskedSignOutStillReachesItsHandlerWithTheSession() {
    fixture.renewalFailsWith("server_error");

    assertThat(run(exchange(MockServerHttpRequest.post(SessionPaths.SIGN_OUT))))
        .isEqualTo(Reached.WITH_SESSION);
    // Only sign-out: another unsafe call is not served.
    MockServerWebExchange other = exchange(MockServerHttpRequest.post("/api/anything"));
    assertThat(run(other)).isNull();
    assertThat(other.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
  }

  @Test
  void aSessionTheProviderRefusesIsRemovedFromTheRequestAndRecorded() {
    fixture.renewalFailsWith("invalid_grant");

    assertThat(run(exchange(MockServerHttpRequest.get("/api/anything"))))
        .isEqualTo(Reached.WITHOUT_SESSION);
    assertThat(session.isExpired()).isTrue();
    assertThat(fixture.actions()).containsExactly("session.expire");
  }

  @Test
  void aRequestWithoutASessionIsNotLookedAt() {
    fixture.renewalFailsWith("server_error");
    AtomicReference<Reached> reached = new AtomicReference<>();
    MockServerWebExchange exchange = exchange(MockServerHttpRequest.get("/api/anything"));

    filter.filter(exchange, chain(reached)).block(SessionFixture.CALL);

    assertThat(reached).hasValue(Reached.WITHOUT_SESSION);
  }

  private MockServerWebExchange exchange(MockServerHttpRequest.BaseBuilder<?> request) {
    return fixture.exchange(request, session);
  }

  private Reached run(MockServerWebExchange exchange) {
    AtomicReference<Reached> reached = new AtomicReference<>();
    filter
        .filter(exchange, chain(reached))
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))
        .block(SessionFixture.CALL);
    return reached.get();
  }

  private static WebFilterChain chain(AtomicReference<Reached> reached) {
    return exchange ->
        ReactiveSecurityContextHolder.getContext()
            .hasElement()
            .doOnNext(
                present -> reached.set(present ? Reached.WITH_SESSION : Reached.WITHOUT_SESSION))
            .then();
  }
}
