package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.access.adapter.web.SessionFixture.Outcome;
import com.aisquad.owlmast.access.adapter.web.SessionKeeper.ProviderSession;
import com.aisquad.owlmast.access.adapter.web.SessionKeeper.Standing;
import java.time.Duration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

/**
 * What becomes of a signed-in session when the identity provider renews it, refuses it or cannot be
 * asked; when it idles out of memory; when a second sign-in completes on it; and at sign-out when
 * the provider does not confirm. The provider's answers are chosen by the test (see {@link
 * SessionFixture}); the real Keycloak answers are exercised in {@code SignInIT}.
 */
class SessionKeeperTest {

  private final SessionFixture fixture = new SessionFixture();

  @AfterEach
  void stop() {
    fixture.close();
  }

  @Test
  void aRenewedSessionStands() {
    Signed signed = signedIn("ref-1", "ada");
    fixture.renewalSucceeds();

    assertThat(standing(signed)).isEqualTo(Standing.CURRENT);
    assertThat(signed.session().isExpired()).isFalse();
    assertThat(fixture.actions()).isEmpty();
  }

  /** The provider failed or refused this backend: nothing is known about the session. */
  @ParameterizedTest
  @ValueSource(
      strings = {
        "server_error",
        "temporarily_unavailable",
        "invalid_token_response",
        "invalid_client",
        "unauthorized_client"
      })
  void aSessionTheProviderCannotBeAskedAboutIsKept(String errorCode) {
    Signed signed = signedIn("ref-1", "ada");
    fixture.renewalFailsWith(errorCode);

    assertThat(standing(signed)).isEqualTo(Standing.UNVERIFIABLE);
    assertThat(signed.session().isExpired()).isFalse();
    assertThat(fixture.registry.size()).isEqualTo(1);
    assertThat(fixture.actions()).isEmpty();
    // Once the provider answers again the same session stands.
    fixture.renewalSucceeds();
    assertThat(standing(signed)).isEqualTo(Standing.CURRENT);
  }

  @Test
  void aProviderThatDoesNotAnswerIsAnOutageToo() {
    Signed signed = signedIn("ref-1", "ada");
    fixture.renewal.set(() -> Mono.error(new java.net.ConnectException("refused")));

    assertThat(standing(signed)).isEqualTo(Standing.UNVERIFIABLE);
    assertThat(signed.session().isExpired()).isFalse();
    assertThat(fixture.actions()).isEmpty();
  }

  @Test
  void aSessionWhoseGrantTheProviderRefusesEnds() {
    Signed signed = signedIn("ref-1", "ada");
    fixture.renewalFailsWith("invalid_grant");

    assertThat(standing(signed)).isEqualTo(Standing.ENDED);
    assertThat(signed.session().isExpired()).isTrue();
    assertThat(fixture.registry.size()).isZero();
    assertThat(fixture.outcomes)
        .containsExactly(new Outcome("session.expire", "SUCCEEDED", "person:ada", null));
  }

  @Test
  void aSessionWithoutTokensEnds() {
    Signed signed = signedIn("ref-1", "ada");
    fixture.renewal.set(Mono::empty);

    assertThat(standing(signed)).isEqualTo(Standing.ENDED);
    assertThat(fixture.actions()).containsExactly("session.expire");
  }

  @Test
  void anIdleSessionIsRecordedOnceWhenTheStoreDropsIt() {
    fixture.keeper.sweep().block(SessionFixture.CALL);
    Signed idle = signedIn("ref-1", "ada");
    assertThat(idle.session().getMaxIdleTime()).isEqualTo(SessionKeeper.MEMORY_BOUND);

    // Just short of the bound nothing is dropped.
    fixture.clock.advance(SessionKeeper.MEMORY_BOUND.minusMinutes(1));
    fixture.keeper.sweep().block(SessionFixture.CALL);
    assertThat(fixture.actions()).isEmpty();

    fixture.clock.advance(Duration.ofMinutes(2));
    Signed fresh = signedIn("ref-2", "grace");
    fixture.keeper.sweep().block(SessionFixture.CALL);
    assertThat(fixture.outcomes)
        .containsExactly(new Outcome("session.expire", "SUCCEEDED", "person:ada", null));
    assertThat(fixture.registry.size()).isEqualTo(1);
    assertThat(fixture.store.getSessions()).doesNotContainKey(idle.session().getId());

    // A second sweep inside the interval looks at nothing, even with a session to record.
    fresh.session().invalidate().block(SessionFixture.CALL);
    fixture.clock.advance(SessionKeeper.SWEEP_INTERVAL.minusSeconds(1));
    fixture.keeper.sweep().block(SessionFixture.CALL);
    assertThat(fixture.actions()).containsExactly("session.expire");
    assertThat(fixture.registry.size()).isEqualTo(1);

    fixture.clock.advance(Duration.ofSeconds(2));
    fixture.keeper.sweep().block(SessionFixture.CALL);
    assertThat(fixture.actions()).containsExactly("session.expire", "session.expire");
    assertThat(fixture.registry.size()).isZero();
  }

  @Test
  void aSecondSignInOnOneSessionTakesTheFirstOnesPlace() {
    WebSession session = fixture.session();
    fixture.keeper.started(session, fixture.person("ref-1", "ada")).block(SessionFixture.CALL);
    assertThat(fixture.actions()).isEmpty();

    fixture.keeper.started(session, fixture.person("ref-2", "ada")).block(SessionFixture.CALL);

    assertThat(fixture.outcomes)
        .containsExactly(new Outcome("session.replace", "SUCCEEDED", "person:ada", null));
    assertThat(fixture.registry.size()).isEqualTo(1);
    assertThat(fixture.registry.remove("ref-2")).isPresent();
    assertThat(session.isExpired()).isFalse();
  }

  @Test
  void signOutWithoutARefreshTokenEndsTheSessionAndIsUnconfirmed() {
    Signed signed = signedIn("ref-1", "ada");
    fixture
        .authorizedClients
        .saveAuthorizedClient(
            fixture.client("ada", false), signed.authentication(), signed.exchange())
        .block(SessionFixture.CALL);

    assertThat(signOut(signed)).isEqualTo(ProviderSession.UNCONFIRMED);

    assertThat(signed.session().isExpired()).isTrue();
    assertThat(fixture.registry.size()).isZero();
    assertThat(fixture.actions()).containsExactly("session.sign-out");
    assertThat(fixture.logoutCalls).hasValue(0);
  }

  @Test
  void signOutWhenTheProvidersLogoutFailsEndsTheSessionAndIsUnconfirmed() {
    Signed signed = signedIn("ref-1", "ada");
    saveTokens(signed);
    fixture.logoutStatus.set(500);

    assertThat(signOut(signed)).isEqualTo(ProviderSession.UNCONFIRMED);

    assertThat(signed.session().isExpired()).isTrue();
    assertThat(fixture.actions()).containsExactly("session.sign-out");
    assertThat(fixture.logoutCalls).hasValue(1);
  }

  @Test
  void signOutThatTheProviderConfirmsIsEnded() {
    Signed signed = signedIn("ref-1", "ada");
    saveTokens(signed);

    assertThat(signOut(signed)).isEqualTo(ProviderSession.ENDED);

    assertThat(signed.session().isExpired()).isTrue();
    assertThat(fixture.actions()).containsExactly("session.sign-out");
    assertThat(fixture.logoutCalls).hasValue(1);
  }

  private record Signed(
      WebSession session,
      OAuth2AuthenticationToken authentication,
      MockServerWebExchange exchange) {}

  private Signed signedIn(String sessionRef, String subject) {
    WebSession session = fixture.session();
    SignedInPerson person = fixture.person(sessionRef, subject);
    fixture.keeper.started(session, person).block(SessionFixture.CALL);
    return new Signed(
        session,
        SessionFixture.authentication(person),
        fixture.exchange(MockServerHttpRequest.get("/api/anything"), session));
  }

  private void saveTokens(Signed signed) {
    fixture
        .authorizedClients
        .saveAuthorizedClient(
            fixture.client("ada", true), signed.authentication(), signed.exchange())
        .block(SessionFixture.CALL);
  }

  private Standing standing(Signed signed) {
    return fixture
        .keeper
        .standing(signed.exchange(), signed.session(), signed.authentication())
        .block(SessionFixture.CALL);
  }

  private ProviderSession signOut(Signed signed) {
    return fixture
        .keeper
        .signOut(signed.exchange(), signed.session(), signed.authentication())
        .block(SessionFixture.CALL);
  }
}
