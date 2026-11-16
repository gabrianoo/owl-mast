package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import com.aisquad.owlmast.access.application.SessionLedger;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.util.Map;
import java.util.Set;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

/**
 * What happens when the identity provider returns the browser (success, refusal, outage) and when
 * the provider cannot be reached at any other step of the security chain. Each unsuccessful end is
 * recorded once, leaves no session behind, and is answered by {@link SignInResponses}.
 *
 * <p>The reason of a refusal is one of this class's fixed codes. The provider's own error code
 * arrives in the callback address, which anyone can write, so it is only looked up, never recorded.
 */
@Slf4j
@RequiredArgsConstructor
final class SignInOutcomeHandlers {

  static final String REASON_REFUSED = "sign-in-refused";
  static final String REASON_UNMATCHED = "authorization-response-unmatched";

  /** Provider or framework error codes, looked up to one of our own reason codes. */
  private static final Map<String, String> REASONS =
      Map.of(
          OAuth2ErrorCodes.ACCESS_DENIED,
          "sign-in-declined",
          "authorization_request_not_found",
          "authorization-response-unmatched",
          "invalid_state_parameter",
          "authorization-response-unmatched",
          OAuth2ErrorCodes.INVALID_GRANT,
          "authorization-code-rejected",
          "invalid_id_token",
          "id-token-rejected",
          "invalid_nonce",
          "id-token-rejected");

  private static final Set<String> OUTAGE_CODES =
      Set.of(
          OAuth2ErrorCodes.SERVER_ERROR,
          OAuth2ErrorCodes.TEMPORARILY_UNAVAILABLE,
          "invalid_token_response");

  private final SessionKeeper sessions;
  private final SessionLedger ledger;
  private final SignInResponses responses;
  private final ServerCsrfTokenRepository csrfTokens;

  /**
   * The session of a completed sign-in is registered and the browser returns to the shell.
   *
   * <p>The session's CSRF token is created here, not when the shell first asks for it: storing a
   * token replaces the session id, and the shell's first requests after the return run side by
   * side, so the one that caused the replacement would leave the others with an id that no longer
   * names a session. After this answer the cookie does not change again.
   */
  ServerAuthenticationSuccessHandler success() {
    return (WebFilterExchange webFilterExchange, Authentication authentication) -> {
      ServerWebExchange exchange = webFilterExchange.getExchange();
      if (!(authentication.getPrincipal() instanceof SignedInPerson person)) {
        // Cannot happen with this chain's user service; without the person there is no session.
        return discard(exchange).then(responses.unavailable(exchange));
      }
      return exchange
          .getSession()
          .flatMap(session -> sessions.started(session, person))
          .then(
              Mono.defer(() ->
                  csrfTokens
                      .generateToken(exchange)
                      .delayUntil(token -> csrfTokens.saveToken(exchange, token))))
          .then(Mono.defer(() -> responses.completed(exchange)));
    };
  }

  ServerAuthenticationFailureHandler failure() {
    // The filter that calls this also sees every authentication failure raised further down the
    // chain; only a failure of the callback itself is the end of a sign-in.
    return (WebFilterExchange webFilterExchange, AuthenticationException failure) ->
        SessionPaths.CALLBACK.equals(webFilterExchange.getExchange().getRequest().getPath().value())
            ? signInEnded(webFilterExchange.getExchange(), failure)
            : Mono.error(failure);
  }

  /**
   * Catches an identity provider that could not be reached anywhere below this filter (starting a
   * sign-in, completing one, fetching signing keys for a bearer credential) and a session store
   * with no room for a new sign-in, and answers 5xx without detail. On the two sign-in addresses it
   * is the end of a sign-in: recorded, the pending session dropped, a browser returned to the
   * shell's provider-error state.
   */
  WebFilter providerOutage() {
    return (ServerWebExchange exchange, WebFilterChain chain) ->
        chain
            .filter(exchange)
            .onErrorResume(
                failure ->
                    failure instanceof IdentityProviderUnavailableException
                        || failure instanceof SessionCapacityExceededException,
                outage -> {
                  String path = exchange.getRequest().getPath().value();
                  if (SessionPaths.SIGN_IN.equals(path) || SessionPaths.CALLBACK.equals(path)) {
                    return signInEnded(exchange, outage);
                  }
                  log.warn(
                      "{}Identity provider unavailable: {}",
                      exchange.getLogPrefix(),
                      SafeFailure.describe(outage));
                  return responses.outage(exchange);
                });
  }

  private Mono<Void> signInEnded(ServerWebExchange exchange, Throwable failure) {
    String correlationId = exchange.getRequest().getId();
    boolean outage = outage(failure);
    log.warn(
        "{}Sign-in did not complete ({}): {}",
        exchange.getLogPrefix(),
        outage ? "outage" : "refused",
        SafeFailure.describe(failure));
    String reason = reason(failure);
    Mono<Void> recorded =
        outage
            ? ledger.signInFailed(failure, correlationId)
            : ledger.signInRefused(reason, correlationId);
    // An answer that matches no sign-in this browser started proves nothing about the sign-ins
    // it did start (anyone can send a browser to the callback address): those stay pending.
    Mono<Void> dropped =
        !outage && REASON_UNMATCHED.equals(reason) ? Mono.empty() : discard(exchange);
    return dropped
        .then(recorded)
        .then(
            Mono.defer(
                () -> outage ? responses.unavailable(exchange) : responses.refused(exchange)));
  }

  /**
   * No partial session: whatever the unfinished sign-in stored is dropped. A session somebody is
   * signed in with is left alone: a callback that fails (anyone can send a browser to that address)
   * must not sign a person out.
   */
  private static Mono<Void> discard(ServerWebExchange exchange) {
    return exchange
        .getSession()
        .filter(session ->
            !session
                .getAttributes()
                .containsKey(
                    WebSessionServerSecurityContextRepository
                        .DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME))
        .flatMap(WebSession::invalidate);
  }

  private static boolean outage(Throwable failure) {
    if (failure instanceof OAuth2AuthenticationException oauth) {
      return OUTAGE_CODES.contains(oauth.getError().getErrorCode());
    }
    return !(failure instanceof AuthenticationException)
        || failure instanceof AuthenticationServiceException;
  }

  private static String reason(Throwable failure) {
    return failure instanceof OAuth2AuthenticationException oauth
        ? REASONS.getOrDefault(oauth.getError().getErrorCode(), REASON_REFUSED)
        : REASON_REFUSED;
  }
}
