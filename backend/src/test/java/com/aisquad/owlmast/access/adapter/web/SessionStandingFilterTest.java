package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.json.JsonParserFactory;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.DefaultCsrfToken;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

/**
 * What a request with a signed-in session gets, by the session's standing: served, served without
 * the session, or 503. The interesting row is the provider that cannot be asked: a protected call
 * is not served and not turned into "signed out", public content is still served, sign-out still
 * reaches its handler with the session, and the session read says how to send that sign-out.
 */
class SessionStandingFilterTest {

  /** What the rest of the chain saw: null when it was not reached. */
  private enum Reached {
    WITH_SESSION,
    WITHOUT_SESSION
  }

  private static final String CSRF_HEADER = "X-CSRF-TOKEN";
  private static final String CSRF_TOKEN = "synthetic-csrf-token";

  private final SessionFixture fixture = new SessionFixture();
  private final WebFilter filter =
      SessionWebFilters.standing(
          fixture.keeper,
          fixture.responses,
          new PathPatternParserServerWebExchangeMatcher("/api/compatibility", HttpMethod.GET),
          new PathPatternParserServerWebExchangeMatcher(SessionPaths.SIGN_OUT, HttpMethod.POST),
          new PathPatternParserServerWebExchangeMatcher(SessionPaths.SESSION, HttpMethod.GET));
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

  /**
   * PR #194 review, R4-5: a sign-out does not ask for the session's standing, so inside the renewal
   * window it does not wait for a provider that never answers the renewal. The renewal here would
   * hold the request for the provider timeout (10 s); the sign-out reaches its handler at once and
   * the provider is not asked.
   */
  @Test
  void aSignOutDoesNotWaitForARenewalTheProviderNeverAnswers() {
    AtomicInteger renewals = new AtomicInteger();
    fixture.renewal.set(() -> {
      renewals.incrementAndGet();
      return Mono.never();
    });
    AtomicReference<Reached> reached = new AtomicReference<>();

    filter
        .filter(exchange(MockServerHttpRequest.post(SessionPaths.SIGN_OUT)), chain(reached))
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))
        .block(Duration.ofSeconds(2));

    assertThat(reached).hasValue(Reached.WITH_SESSION);
    assertThat(renewals).hasValue(0);
    assertThat(session.isExpired()).isFalse();
    assertThat(fixture.actions()).isEmpty();
  }

  /**
   * R4-5, the other verdict: the sign-out of a session the provider would refuse to renew also
   * reaches its handler with the session, which ends it as a sign-out, not as "expired".
   */
  @Test
  void aSignOutReachesItsHandlerWithTheSessionWhateverTheProviderWouldSay() {
    fixture.renewalFailsWith("invalid_grant");

    assertThat(run(exchange(MockServerHttpRequest.post(SessionPaths.SIGN_OUT))))
        .isEqualTo(Reached.WITH_SESSION);
    assertThat(session.isExpired()).isFalse();
    assertThat(fixture.actions()).isEmpty();
  }

  /**
   * PR #194 review, R2-3: a shell that starts during the outage has no CSRF token and cannot tell
   * that a session is kept, so it could not offer or send the sign-out the backend serves. The
   * session read now says both in its 503.
   */
  @Test
  void whenTheProviderCannotBeAskedTheSessionReadCarriesTheCsrfTokenOfTheKeptSession() {
    fixture.renewalFailsWith("server_error");

    MockServerWebExchange exchange = exchange(MockServerHttpRequest.get(SessionPaths.SESSION));
    prepareCsrfToken(exchange);
    assertThat(run(exchange)).isNull();

    assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    assertThat(exchange.getResponse().getHeaders().getContentType())
        .hasToString("application/problem+json");
    assertThat(exchange.getResponse().getHeaders().getCacheControl()).isEqualTo("no-store");
    // The envelope with one extension member at its top level, and nothing about the person.
    assertThat(body(exchange))
        .containsOnlyKeys("title", "status", "instance", "csrf")
        .containsEntry("status", 503)
        .containsEntry("instance", SessionPaths.SESSION)
        .containsEntry("csrf", Map.of("headerName", CSRF_HEADER, "token", CSRF_TOKEN));
    assertThat(session.isExpired()).isFalse();
    assertThat(fixture.actions()).isEmpty();
  }

  @Test
  void onlyTheSessionReadCarriesTheCsrfTokenAndOnlyWhenOneWasPrepared() {
    fixture.renewalFailsWith("server_error");

    // Another call of the same session: the plain outage.
    MockServerWebExchange other = exchange(MockServerHttpRequest.get("/api/anything"));
    prepareCsrfToken(other);
    assertThat(run(other)).isNull();
    assertThat(other.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    assertThat(body(other)).doesNotContainKey("csrf");
    // The session read of a request the CSRF filter prepared no token for.
    MockServerWebExchange unprepared = exchange(MockServerHttpRequest.get(SessionPaths.SESSION));
    assertThat(run(unprepared)).isNull();
    assertThat(unprepared.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    assertThat(body(unprepared)).doesNotContainKey("csrf");
    // A session that stands is read by the controller, not answered here.
    fixture.renewalSucceeds();
    MockServerWebExchange standing = exchange(MockServerHttpRequest.get(SessionPaths.SESSION));
    prepareCsrfToken(standing);
    assertThat(run(standing)).isEqualTo(Reached.WITH_SESSION);
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

  /** What the CSRF filter leaves in the exchange before this filter runs. */
  private static void prepareCsrfToken(MockServerWebExchange exchange) {
    exchange
        .getAttributes()
        .put(
            CsrfToken.class.getName(),
            Mono.<CsrfToken>just(new DefaultCsrfToken(CSRF_HEADER, "_csrf", CSRF_TOKEN)));
  }

  private static Map<String, Object> body(MockServerWebExchange exchange) {
    return JsonParserFactory.getJsonParser()
        .parseMap(exchange.getResponse().getBodyAsString().block(SessionFixture.CALL));
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
