package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;
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
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;

/**
 * The checks every presented credential passes after its signature: expiry, issuer, audience, kind
 * and subject, each refusal under its fixed code. Signature verification against the issuer's keys
 * is proven with the real Keycloak in {@code SignInIT}; a credential past its lifetime is proven
 * here, because a token Keycloak signed cannot be made old.
 */
class CredentialValidationTest {

  private static final String ISSUER = "https://id.example/realms/owl-mast";
  private static final String CLIENT = "owl-mast-web";

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
    assertThat(CredentialValidation.couldNotVerify(new IllegalStateException("other"))).isFalse();
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
