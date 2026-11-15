package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.access.adapter.identity.IdentityDiscovery;
import com.aisquad.owlmast.access.adapter.identity.IdentityProperties;
import com.aisquad.owlmast.access.adapter.identity.IssuerSigningKeys;
import com.aisquad.owlmast.access.adapter.identity.SigningIssuer;
import com.aisquad.owlmast.access.adapter.identity.SigningIssuer.Answer;
import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import com.aisquad.owlmast.testing.StubIdentityProvider;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.scheduler.VirtualTimeScheduler;

/**
 * The checks every presented credential passes after its signature: expiry, issuer, audience, kind
 * and subject, each refusal under its fixed code; and what the decoder makes of the issuer's keys:
 * a signature that verifies, a key the issuer does not have, keys that cannot be fetched.
 * Verification against Keycloak's own keys and tokens is proven in {@code SignInIT}; a credential
 * past its lifetime is proven here, because a token Keycloak signed cannot be made old.
 */
class CredentialValidationTest {

  private static final String ISSUER = "https://id.example/realms/owl-mast";
  private static final String CLIENT = "owl-mast-web";

  /** Real-time bound for one answer of a local issuer; never part of a timing assertion. */
  private static final Duration ANSWER = Duration.ofSeconds(30);

  private final OAuth2TokenValidator<Jwt> bearer = CredentialValidation.bearer(ISSUER, CLIENT);
  private final OAuth2TokenValidator<Jwt> logout = CredentialValidation.logoutToken(ISSUER, CLIENT);

  @Test
  void aCurrentCredentialOfThisIssuerAndAudienceIsAccepted() {
    assertThat(bearer.validate(accessToken(claims -> {})).hasErrors()).isFalse();
    // Other audiences beside ours do not matter; a token that does not say its kind is accepted.
    assertThat(
            bearer
                .validate(
                    accessToken(claims -> {
                      claims.put("aud", List.of("account", CLIENT));
                      claims.remove("typ");
                    }))
                .hasErrors())
        .isFalse();
  }

  @Test
  void anExpiredOrNotYetValidCredentialIsRefused() {
    Instant now = Instant.now();
    // Beyond the validator's allowance for clock differences (one minute).
    assertThat(
            reason(
                bearer,
                token(
                    now.minusSeconds(900),
                    now.minusSeconds(120),
                    claims -> claims.put("typ", "Bearer"))))
        .isEqualTo(CredentialValidation.REASON_EXPIRED);
    assertThat(
            reason(
                bearer,
                token(
                    now, now.plusSeconds(900), claims -> claims.put("nbf", now.plusSeconds(600)))))
        .isEqualTo(CredentialValidation.REASON_EXPIRED);
    assertThat(reason(logout, token(now.minusSeconds(900), now.minusSeconds(120), logoutClaims())))
        .isEqualTo(CredentialValidation.REASON_EXPIRED);
  }

  /** The framework's timestamp check alone accepts a token that never expires. */
  @Test
  void aCredentialWithoutAnExpiryIsRefused() {
    assertThat(reason(bearer, accessToken(claims -> claims.remove("exp"))))
        .isEqualTo(CredentialValidation.REASON_EXPIRED);
    assertThat(
            reason(
                logout,
                token(
                    Instant.now(),
                    Instant.now().plusSeconds(60),
                    logoutClaims().andThen(claims -> claims.remove("exp")))))
        .isEqualTo(CredentialValidation.REASON_EXPIRED);
  }

  /** Keys that could not be fetched say nothing about the token; a bad token does. */
  @Test
  void aFailureToFetchKeysIsNotARefusal() {
    // What the framework makes of a key fetch that failed (spring-security-oauth2-jose 7.1.2): its
    // own IllegalStateException around the failure of IssuerSigningKeys.
    assertThat(
            CredentialValidation.couldNotVerify(
                new IllegalStateException(
                    "Could not obtain the keys",
                    new IdentityProviderUnavailableException(new IllegalStateException("5xx")))))
        .isTrue();
    assertThat(
            CredentialValidation.couldNotVerify(
                new JwtException("An error occurred while attempting to decode the Jwt")))
        .isTrue();
    assertThat(
            CredentialValidation.couldNotVerify(
                new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_id_token"), new JwtException("keys"))))
        .isTrue();
    assertThat(CredentialValidation.couldNotVerify(new BadJwtException("signature"))).isFalse();
    assertThat(
            CredentialValidation.couldNotVerify(
                new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_id_token"),
                    new JwtValidationException(
                        "expired", List.of(new OAuth2Error("invalid_token"))))))
        .isFalse();
    // An IllegalStateException that no unavailable provider caused is not an outage.
    assertThat(CredentialValidation.couldNotVerify(new IllegalStateException("other"))).isFalse();
  }

  /**
   * R1-1: the key endpoint answers 5xx or refuses the connection while the discovery document is
   * served. The decoder then fails as an unavailable provider, which every caller answers 503;
   * before, the framework's IllegalStateException reached them and read as a refusal (400 for a
   * logout notice) or as an unhandled failure (500 for a bearer call).
   */
  @Test
  void aKeyFetchThatFailsFastLeavesTheDecoderAsAnUnavailableProvider() {
    try (SigningIssuer issuer = new SigningIssuer()) {
      issuer.keysAre(Answer.FAILING);
      String credential = issuer.sign(issuer.claims(CLIENT, "subject-1"));
      for (OAuth2TokenValidator<Jwt> kind :
          List.of(
              CredentialValidation.bearer(issuer.issuerUri(), CLIENT),
              CredentialValidation.logoutToken(issuer.issuerUri(), CLIENT))) {
        ReactiveJwtDecoder decoder = CredentialValidation.decoder(keysOf(issuer), kind);
        assertThatThrownBy(() -> decoder.decode(credential).block(ANSWER))
            .isInstanceOf(IdentityProviderUnavailableException.class)
            .matches(CredentialValidation::couldNotVerify);
      }
    }
    // A discovery document that names a key endpoint nobody listens on.
    try (StubIdentityProvider provider =
        StubIdentityProvider.startWithUnreachableEndpoints("owl-mast")) {
      ReactiveJwtDecoder decoder =
          CredentialValidation.decoder(
              new IssuerSigningKeys(
                  WebClient.create(),
                  new IdentityDiscovery(
                      WebClient.create(), new IdentityProperties(provider.issuerUri(), true))),
              CredentialValidation.bearer(provider.issuerUri(), CLIENT));
      try (SigningIssuer somebody = new SigningIssuer()) {
        String credential = somebody.sign(somebody.claims(CLIENT, "subject-1"));
        assertThatThrownBy(() -> decoder.decode(credential).block(ANSWER))
            .isInstanceOf(IdentityProviderUnavailableException.class);
      }
    }
  }

  @Test
  void aCredentialTheIssuerSignedIsVerifiedAgainstItsKeysAndThenChecked() {
    try (SigningIssuer issuer = new SigningIssuer()) {
      ReactiveJwtDecoder decoder =
          CredentialValidation.decoder(
              keysOf(issuer), CredentialValidation.bearer(issuer.issuerUri(), CLIENT));

      Jwt accepted = decoder.decode(issuer.sign(issuer.claims(CLIENT, "subject-1"))).block(ANSWER);
      assertThat(accepted).isNotNull();
      assertThat(accepted.getSubject()).isEqualTo("subject-1");

      // Signed by the issuer, for another audience: refused under its code, not an outage.
      assertThatThrownBy(
              () -> decoder.decode(issuer.sign(issuer.claims("account", "s"))).block(ANSWER))
          .isInstanceOf(JwtValidationException.class)
          .matches(failure -> !CredentialValidation.couldNotVerify(failure))
          .matches(failure ->
              CredentialValidation.reasonOf(failure).equals(CredentialValidation.REASON_AUDIENCE));
      // The issuer's key id on a signature that is not the issuer's.
      assertThatThrownBy(
              () -> decoder.decode(issuer.forged(issuer.claims(CLIENT, "s"))).block(ANSWER))
          .isInstanceOf(BadJwtException.class);
      // Not a token at all: a refusal as a signal, never a thrown exception.
      assertThatThrownBy(() -> decoder.decode("not-a-token").block(ANSWER))
          .isInstanceOf(BadJwtException.class);
      assertThat(issuer.keyRequests()).isEqualTo(1);
    }
  }

  /** Without an accepted discovery document nothing presented is judged, a non-token included. */
  @Test
  void whileNoDiscoveryDocumentWasAcceptedEveryCredentialIsAnOutage() {
    String nowhere = StubIdentityProvider.UNREACHABLE + "/realms/owl-mast";
    ReactiveJwtDecoder decoder =
        CredentialValidation.decoder(
            new IssuerSigningKeys(
                WebClient.create(),
                new IdentityDiscovery(WebClient.create(), new IdentityProperties(nowhere, true))),
            CredentialValidation.bearer(nowhere, CLIENT));
    assertThatThrownBy(() -> decoder.decode("not-a-token").block(ANSWER))
        .isInstanceOf(IdentityProviderUnavailableException.class);
  }

  /**
   * R1-3: anybody can present tokens that name keys the issuer does not have. Each is refused, and
   * together they cost the identity provider one key request, across both kinds of credential.
   */
  @Test
  void credentialsNamingUnknownKeysAreRefusedAndCostTheIssuerOneKeyRequest() {
    try (SigningIssuer issuer = new SigningIssuer()) {
      IssuerSigningKeys keys = keysOf(issuer);
      ReactiveJwtDecoder bearerDecoder =
          CredentialValidation.decoder(
              keys, CredentialValidation.bearer(issuer.issuerUri(), CLIENT));
      ReactiveJwtDecoder logoutDecoder =
          CredentialValidation.decoder(
              keys, CredentialValidation.logoutToken(issuer.issuerUri(), CLIENT));
      for (int i = 0; i < 25; i++) {
        for (ReactiveJwtDecoder decoder : List.of(bearerDecoder, logoutDecoder)) {
          String credential = issuer.signedBySomebodyElse(issuer.claims(CLIENT, "subject-1"));
          assertThatThrownBy(() -> decoder.decode(credential).block(ANSWER))
              .isInstanceOf(BadJwtException.class)
              .matches(failure -> !CredentialValidation.couldNotVerify(failure))
              .matches(failure ->
                  CredentialValidation.reasonOf(failure)
                      .equals(CredentialValidation.REASON_INVALID));
        }
      }
      assertThat(issuer.keyRequests()).isEqualTo(1);
      // The issuer's own credentials are still accepted, without another request.
      assertThat(
              bearerDecoder.decode(issuer.sign(issuer.claims(CLIENT, "subject-1"))).block(ANSWER))
          .isNotNull();
      assertThat(issuer.keyRequests()).isEqualTo(1);
    }
  }

  /** The step is bounded on the given clock, and what it bounds ends as an unavailable provider. */
  @Test
  void aProviderStepThatIsNotAnsweredInTimeIsAnOutage() {
    VirtualTimeScheduler time = VirtualTimeScheduler.create();
    CompletableFuture<String> unanswered =
        CredentialValidation.withinProviderTimeout(
                Mono.<String>never(), CredentialValidation.PROVIDER_TIMEOUT, time)
            .toFuture();
    time.advanceTimeBy(CredentialValidation.PROVIDER_TIMEOUT.minusMillis(1));
    assertThat(unanswered).isNotDone();
    time.advanceTimeBy(Duration.ofMillis(1));
    assertThat(unanswered)
        .isCompletedExceptionally()
        .failsWithin(Duration.ZERO)
        .withThrowableThat()
        .withCauseInstanceOf(IdentityProviderUnavailableException.class);
    // An answer in time passes through, and so does a failure that is not the time running out.
    assertThat(
            CredentialValidation.withinProviderTimeout(
                    Mono.just("answer"), CredentialValidation.PROVIDER_TIMEOUT, time)
                .block(ANSWER))
        .isEqualTo("answer");
    assertThatThrownBy(() ->
            CredentialValidation.withinProviderTimeout(
                    Mono.error(new BadJwtException("signature")),
                    CredentialValidation.PROVIDER_TIMEOUT,
                    time)
                .block(ANSWER))
        .isInstanceOf(BadJwtException.class);
  }

  private static IssuerSigningKeys keysOf(SigningIssuer issuer) {
    return new IssuerSigningKeys(
        WebClient.create(),
        new IdentityDiscovery(
            WebClient.create(), new IdentityProperties(issuer.issuerUri(), true)));
  }

  @Test
  void anotherIssuerIsRefused() {
    for (String issuer :
        List.of(
            "https://id.example/realms/other",
            ISSUER + "/",
            "https://id.example/realms/OWL-MAST",
            "http://id.example/realms/owl-mast")) {
      assertThat(reason(bearer, accessToken(claims -> claims.put("iss", issuer))))
          .as(issuer)
          .isEqualTo(CredentialValidation.REASON_ISSUER);
    }
    assertThat(reason(bearer, accessToken(claims -> claims.remove("iss"))))
        .isEqualTo(CredentialValidation.REASON_ISSUER);
  }

  @Test
  void anotherAudienceIsRefused() {
    assertThat(reason(bearer, accessToken(claims -> claims.put("aud", List.of("account")))))
        .isEqualTo(CredentialValidation.REASON_AUDIENCE);
    assertThat(reason(bearer, accessToken(claims -> claims.remove("aud"))))
        .isEqualTo(CredentialValidation.REASON_AUDIENCE);
    assertThat(reason(bearer, accessToken(claims -> claims.put("aud", List.of(CLIENT + "2")))))
        .isEqualTo(CredentialValidation.REASON_AUDIENCE);
    assertThat(
            reason(
                logout,
                token(
                    Instant.now(),
                    Instant.now().plusSeconds(60),
                    logoutClaims().andThen(claims -> claims.put("aud", List.of("other"))))))
        .isEqualTo(CredentialValidation.REASON_AUDIENCE);
  }

  /**
   * The issuer signs ID, refresh and logout tokens with the same key, and an ID token carries the
   * client as its audience: none of them is a bearer credential.
   */
  @Test
  void theIssuersOtherTokenKindsAreNotBearerCredentials() {
    assertThat(reason(bearer, accessToken(claims -> claims.put("typ", "ID"))))
        .isEqualTo(CredentialValidation.REASON_KIND);
    assertThat(reason(bearer, accessToken(claims -> claims.put("typ", "Refresh"))))
        .isEqualTo(CredentialValidation.REASON_KIND);
    assertThat(
            reason(
                bearer,
                accessToken(claims -> {
                  claims.remove("typ");
                  claims.put("nonce", "n");
                })))
        .isEqualTo(CredentialValidation.REASON_KIND);
    assertThat(reason(bearer, token(Instant.now(), Instant.now().plusSeconds(60), logoutClaims())))
        .isEqualTo(CredentialValidation.REASON_KIND);
  }

  @Test
  void aBearerCredentialMustNameItsSubject() {
    assertThat(reason(bearer, accessToken(claims -> claims.remove("sub"))))
        .isEqualTo(CredentialValidation.REASON_SUBJECT);
    assertThat(reason(bearer, accessToken(claims -> claims.put("sub", " "))))
        .isEqualTo(CredentialValidation.REASON_SUBJECT);
  }

  @Test
  void aLogoutTokenCarriesTheLogoutEventAndNamesASessionOrASubject() {
    Instant now = Instant.now();
    assertThat(logout.validate(token(now, now.plusSeconds(60), logoutClaims())).hasErrors())
        .isFalse();
    assertThat(
            logout
                .validate(
                    token(
                        now,
                        now.plusSeconds(60),
                        logoutClaims().andThen(claims -> claims.remove("sid"))))
                .hasErrors())
        .isFalse();
    // An access token, a notice with a nonce, a notice without the event.
    assertThat(reason(logout, accessToken(claims -> {})))
        .isEqualTo(CredentialValidation.REASON_KIND);
    assertThat(
            reason(
                logout,
                token(
                    now,
                    now.plusSeconds(60),
                    logoutClaims().andThen(claims -> claims.put("nonce", "n")))))
        .isEqualTo(CredentialValidation.REASON_KIND);
    assertThat(
            reason(
                logout,
                token(
                    now,
                    now.plusSeconds(60),
                    logoutClaims()
                        .andThen(claims -> claims.put("events", Map.of("other", Map.of()))))))
        .isEqualTo(CredentialValidation.REASON_KIND);
    assertThat(
            reason(
                logout,
                token(
                    now,
                    now.plusSeconds(60),
                    logoutClaims()
                        .andThen(claims -> {
                          claims.remove("sid");
                          claims.remove("sub");
                        }))))
        .isEqualTo(CredentialValidation.REASON_SUBJECT);
  }

  @Test
  void aRefusalThatNamesNoKnownReasonIsReportedAsInvalid() {
    assertThat(CredentialValidation.reasonOf(new BadJwtException("signature")))
        .isEqualTo(CredentialValidation.REASON_INVALID);
    assertThat(CredentialValidation.reasonOf(new IllegalStateException("anything")))
        .isEqualTo(CredentialValidation.REASON_INVALID);
    // A description that is not one of ours (it could come from a library) is never passed on.
    assertThat(
            CredentialValidation.reasonOf(
                new InvalidBearerTokenException(
                    "x",
                    new JwtValidationException(
                        "x", List.of(new OAuth2Error("invalid_token", "attacker text", null))))))
        .isEqualTo(CredentialValidation.REASON_INVALID);
  }

  /** The code the decoder would report: it raises a JwtValidationException with these errors. */
  private static String reason(OAuth2TokenValidator<Jwt> validator, Jwt jwt) {
    OAuth2TokenValidatorResult result = validator.validate(jwt);
    assertThat(result.hasErrors()).isTrue();
    return CredentialValidation.reasonOf(
        new InvalidBearerTokenException(
            "refused", new JwtValidationException("refused", result.getErrors())));
  }

  private static Jwt accessToken(Consumer<Map<String, Object>> change) {
    Instant now = Instant.now();
    return token(
        now,
        now.plusSeconds(300),
        claims -> {
          claims.put("typ", "Bearer");
          change.accept(claims);
        });
  }

  private static Consumer<Map<String, Object>> logoutClaims() {
    return claims -> {
      claims.put("typ", "Logout");
      claims.put("sid", "provider-session");
      claims.put("events", Map.of(CredentialValidation.LOGOUT_EVENT, Map.of()));
    };
  }

  private static Jwt token(
      Instant issuedAt, Instant expiresAt, Consumer<Map<String, Object>> change) {
    return Jwt.withTokenValue("synthetic")
        .header("alg", "RS256")
        .claims(claims -> {
          claims.put("iss", ISSUER);
          claims.put("sub", "subject-1");
          claims.put("aud", List.of(CLIENT));
          claims.put("iat", issuedAt);
          claims.put("exp", expiresAt);
          change.accept(claims);
        })
        .build();
  }
}
