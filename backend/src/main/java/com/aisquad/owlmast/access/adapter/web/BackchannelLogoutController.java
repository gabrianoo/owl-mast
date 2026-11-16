package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.util.Optional;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * OpenID Connect Back-Channel Logout 1.0: the identity provider posts a signed logout token when a
 * session ended there (the person signed out elsewhere, an administrator ended the session), and
 * the sessions it names end here at once. The request is authenticated by the token alone, so the
 * endpoint is public and takes no CSRF token: a caller without the provider's signing key gets 400
 * and changes nothing. A valid notice answers 200 whether or not a session was still open. A notice
 * that cannot be verified because the provider's keys cannot be fetched answers 503: the provider
 * retries it.
 */
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@Slf4j
@RestController
class BackchannelLogoutController {

  static final String TOKEN_PARAMETER = "logout_token";

  /** Longer than any logout token; a larger value is refused before it is parsed. */
  static final int MAX_TOKEN_LENGTH = 16_384;

  private final ReactiveJwtDecoder logoutTokens;
  private final SessionKeeper sessions;

  BackchannelLogoutController(ReactiveJwtDecoder logoutTokenDecoder, SessionKeeper sessions) {
    this.logoutTokens = logoutTokenDecoder;
    this.sessions = sessions;
  }

  @PostMapping(
      path = SessionPaths.BACKCHANNEL_LOGOUT,
      consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
  Mono<ResponseEntity<Void>> logout(ServerWebExchange exchange) {
    return exchange
        .getFormData()
        .mapNotNull(form -> form.getFirst(TOKEN_PARAMETER))
        .filter(token -> !token.isBlank() && token.length() <= MAX_TOKEN_LENGTH)
        .switchIfEmpty(Mono.error(BackchannelLogoutController::refusedNotice))
        .flatMap(token ->
            logoutTokens
                .decode(token)
                .onErrorMap(failure -> {
                  if (CredentialValidation.couldNotVerify(failure)) {
                    // The notice may be genuine: 503, so that the provider sends it again.
                    log.warn(
                        "{}Logout notice could not be verified: {}",
                        exchange.getLogPrefix(),
                        SafeFailure.describe(failure));
                    return failure instanceof IdentityProviderUnavailableException
                        ? failure
                        : new IdentityProviderUnavailableException(failure);
                  }
                  log.warn(
                      "{}Logout notice refused ({}): {}",
                      exchange.getLogPrefix(),
                      CredentialValidation.reasonOf(failure),
                      SafeFailure.describe(failure));
                  return refusedNotice();
                }))
        .flatMap(this::end)
        .map(ended -> ResponseEntity.ok().cacheControl(CacheControl.noStore()).<Void>build());
  }

  private Mono<Long> end(Jwt notice) {
    Optional<String> providerSessionId =
        Optional.ofNullable(notice.getClaimAsString("sid")).filter(sid -> !sid.isBlank());
    // The validator required a session id or a subject; a notice with only a session id still
    // needs a subject value to build the identity, and that value is then not compared.
    String subject = Optional.ofNullable(notice.getSubject()).filter(s -> !s.isBlank()).orElse("-");
    ExternalIdentity identity;
    try {
      identity = new ExternalIdentity(notice.getClaimAsString("iss"), subject);
    } catch (IllegalArgumentException unusable) {
      return Mono.error(refusedNotice());
    }
    return sessions.revoke(identity, providerSessionId);
  }

  private static ResponseStatusException refusedNotice() {
    return new ResponseStatusException(HttpStatus.BAD_REQUEST);
  }
}
