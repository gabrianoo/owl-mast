package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.adapter.identity.IdentityDiscovery;
import com.aisquad.owlmast.access.adapter.identity.ProviderMetadata;
import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Predicate;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

/**
 * Validation of a signed credential that is presented to the backend directly: a bearer credential
 * on an API call, or the identity provider's logout token. Each is verified against the issuer's
 * signing keys and then checked, in this order, for expiry, issuer and audience, and for the claims
 * that say what kind of token it is. The first check that fails names the refusal with a fixed code
 * ({@link #reasonOf}); the code goes to the audit record and never to the response.
 *
 * <p>The keys come from the discovery document when a credential is first presented (see {@link
 * IdentityDiscovery}); a provider that cannot be reached is an outage (5xx), not a refusal.
 */
final class CredentialValidation {

  static final String REASON_INVALID = "credential-invalid";
  static final String REASON_EXPIRED = "credential-expired";
  static final String REASON_ISSUER = "credential-issuer-mismatch";
  static final String REASON_AUDIENCE = "credential-audience-mismatch";
  static final String REASON_KIND = "credential-kind-mismatch";
  static final String REASON_SUBJECT = "credential-subject-missing";

  /** Keycloak's claim naming the kind of a token it signed; other issuers do not set it. */
  static final String TYPE_CLAIM = "typ";

  static final String BEARER_TYPE = "Bearer";
  private static final int MAX_CAUSE_DEPTH = 8;

  /** How long the identity provider may take to answer one step (keys, code, renewal). */
  static final Duration PROVIDER_TIMEOUT = Duration.ofSeconds(10);

  static final String LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout";

  private CredentialValidation() {}

  /**
   * A bearer credential: unexpired, from the trusted issuer, for this audience, naming a subject,
   * and not one of the issuer's other token kinds. The same key signs ID, refresh and logout
   * tokens, and an ID token even carries the client as its audience, so the kind is checked: a
   * token that says what it is must say {@code Bearer}, and one with a {@code nonce} or a logout
   * event is refused.
   */
  static OAuth2TokenValidator<Jwt> bearer(String issuer, String audience) {
    Map<String, OAuth2TokenValidator<Jwt>> checks = new LinkedHashMap<>();
    checks.put(REASON_EXPIRED, unexpired());
    checks.put(REASON_ISSUER, new JwtIssuerValidator(issuer));
    checks.put(REASON_AUDIENCE, audience(audience));
    checks.put(
        REASON_KIND,
        claims(jwt ->
            Optional.ofNullable(jwt.getClaimAsString(TYPE_CLAIM))
                    .map(BEARER_TYPE::equals)
                    .orElse(true)
                && !jwt.hasClaim("nonce")
                && !jwt.hasClaim("events")));
    checks.put(
        REASON_SUBJECT, claims(jwt -> jwt.getSubject() != null && !jwt.getSubject().isBlank()));
    return ordered(checks);
  }

  /**
   * A logout token (OpenID Connect Back-Channel Logout 1.0, section 2.6): unexpired, from the
   * trusted issuer, for this client, carrying the logout event, naming a session or a subject, and
   * without a {@code nonce}.
   */
  static OAuth2TokenValidator<Jwt> logoutToken(String issuer, String clientId) {
    Map<String, OAuth2TokenValidator<Jwt>> checks = new LinkedHashMap<>();
    checks.put(REASON_EXPIRED, unexpired());
    checks.put(REASON_ISSUER, new JwtIssuerValidator(issuer));
    checks.put(REASON_AUDIENCE, audience(clientId));
    checks.put(
        REASON_KIND,
        claims(jwt ->
            jwt.getClaims().get("events") instanceof Map<?, ?> events
                && events.containsKey(LOGOUT_EVENT)
                && !jwt.hasClaim("nonce")
                && jwt.getIssuedAt() != null));
    checks.put(
        REASON_SUBJECT,
        claims(jwt ->
            (jwt.getSubject() != null && !jwt.getSubject().isBlank())
                || (jwt.getClaimAsString("sid") != null
                    && !jwt.getClaimAsString("sid").isBlank())));
    return ordered(checks);
  }

  /** The fixed code of a refusal, read from what {@link #ordered} put into the failure. */
  static String reasonOf(Throwable failure) {
    Throwable current = failure;
    for (int depth = 0; current != null && depth < MAX_CAUSE_DEPTH; depth++) {
      if (current instanceof JwtValidationException validation) {
        return validation.getErrors().stream()
            .map(OAuth2Error::getDescription)
            .filter(KNOWN_REASONS::contains)
            .findFirst()
            .orElse(REASON_INVALID);
      }
      current = current.getCause();
    }
    return REASON_INVALID;
  }

  private static final List<String> KNOWN_REASONS =
      List.of(REASON_EXPIRED, REASON_ISSUER, REASON_AUDIENCE, REASON_KIND, REASON_SUBJECT);

  /**
   * Whether a failure to verify a token says nothing about the token: the keys could not be fetched
   * (a {@code JwtException} that is not a {@code BadJwtException}) or the provider was unavailable.
   * Such a failure is an outage, never a refusal.
   */
  static boolean couldNotVerify(Throwable failure) {
    Throwable current = failure;
    for (int depth = 0; current != null && depth < MAX_CAUSE_DEPTH; depth++) {
      if (current instanceof IdentityProviderUnavailableException
          || (current instanceof JwtException && !(current instanceof BadJwtException))) {
        return true;
      }
      current = current.getCause();
    }
    return false;
  }

  /** A decoder that finds the issuer's keys when the first credential arrives. */
  static ReactiveJwtDecoder decoder(
      IdentityDiscovery discovery, OAuth2TokenValidator<Jwt> validator) {
    AtomicReference<Map.Entry<String, ReactiveJwtDecoder>> current = new AtomicReference<>();
    return token ->
        discovery
            .metadata()
            .map(ProviderMetadata::jwksUri)
            .map(jwksUri -> {
              Map.Entry<String, ReactiveJwtDecoder> known = current.get();
              if (known != null && known.getKey().equals(jwksUri)) {
                return known.getValue();
              }
              NimbusReactiveJwtDecoder created =
                  NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri).build();
              created.setJwtValidator(validator);
              current.set(Map.entry(jwksUri, created));
              return (ReactiveJwtDecoder) created;
            })
            .flatMap(decoder -> decoder.decode(token))
            // A provider that accepts the connection and never answers with its keys is an
            // outage like one that refuses the connection.
            .timeout(PROVIDER_TIMEOUT)
            .onErrorMap(TimeoutException.class, IdentityProviderUnavailableException::new);
  }

  /**
   * The token carries an expiry and it has not passed. The framework's validator alone accepts a
   * token without {@code exp}; such a token would never expire, so it is refused.
   */
  private static OAuth2TokenValidator<Jwt> unexpired() {
    JwtTimestampValidator timestamps = new JwtTimestampValidator();
    return jwt ->
        jwt.getExpiresAt() == null
            ? OAuth2TokenValidatorResult.failure(new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN))
            : timestamps.validate(jwt);
  }

  private static OAuth2TokenValidator<Jwt> audience(String expected) {
    return new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD, audience -> audience != null && audience.contains(expected));
  }

  private static OAuth2TokenValidator<Jwt> claims(Predicate<Jwt> accepted) {
    return jwt ->
        accepted.test(jwt)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN));
  }

  /** Runs the checks in order and reports the first that fails under its fixed code. */
  private static OAuth2TokenValidator<Jwt> ordered(Map<String, OAuth2TokenValidator<Jwt>> checks) {
    return jwt ->
        checks.entrySet().stream()
            .filter(check -> check.getValue().validate(jwt).hasErrors())
            .findFirst()
            .map(check ->
                OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN, check.getKey(), null)))
            .orElseGet(OAuth2TokenValidatorResult::success);
  }
}
