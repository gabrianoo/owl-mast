package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.adapter.web.SessionKeeper.ProviderSession;
import java.util.LinkedHashMap;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * What the shell reads and does about its session (docs/identity.md).
 *
 * <p>{@code GET /api/session} is public and never answers 401: it says {@code signed-out}, or
 * {@code signed-in} with the person to show and the CSRF token that every unsafe call must send
 * back in the named header. The person is a principal id and a display name; no token, subject,
 * email or username is published. A bearer caller has no browser session and reads {@code
 * signed-out}.
 *
 * <p>{@code POST /api/session/sign-out} ends the session here and at the identity provider and says
 * whether the provider confirmed its part.
 */
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@RestController
@RequiredArgsConstructor
class SessionController {

  static final String SIGNED_OUT = "signed-out";
  static final String SIGNED_IN = "signed-in";

  private final SessionKeeper sessions;
  private final SignInResponses responses;

  /**
   * Reached only by a browser that already has a session (the security chain answers every other
   * request for this path by starting a sign-in): back to the shell.
   */
  @GetMapping(SessionPaths.SIGN_IN)
  Mono<Void> alreadySignedIn(ServerWebExchange exchange) {
    return responses.alreadySignedIn(exchange);
  }

  @GetMapping(path = SessionPaths.SESSION, produces = MediaType.APPLICATION_JSON_VALUE)
  Mono<ResponseEntity<Map<String, Object>>> session(ServerWebExchange exchange) {
    return browserSession()
        .flatMap(authentication ->
            csrfToken(exchange).map(csrf -> signedIn(person(authentication), csrf)))
        .defaultIfEmpty(Map.of("state", SIGNED_OUT))
        .map(SessionController::notStored);
  }

  @PostMapping(path = SessionPaths.SIGN_OUT, produces = MediaType.APPLICATION_JSON_VALUE)
  Mono<ResponseEntity<Map<String, Object>>> signOut(ServerWebExchange exchange) {
    return browserSession()
        // Authenticated, but not by a browser session: there is nothing to sign out of.
        .switchIfEmpty(Mono.error(() -> new ResponseStatusException(HttpStatus.CONFLICT)))
        .flatMap(authentication ->
            exchange
                .getSession()
                .flatMap(session -> sessions.signOut(exchange, session, authentication)))
        .map(provider -> {
          Map<String, Object> body = new LinkedHashMap<>();
          body.put("state", SIGNED_OUT);
          body.put("identityProvider", provider == ProviderSession.ENDED ? "ended" : "unconfirmed");
          return notStored(body);
        });
  }

  private static Mono<OAuth2AuthenticationToken> browserSession() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .ofType(OAuth2AuthenticationToken.class)
        .filter(authentication -> authentication.getPrincipal() instanceof SignedInPerson);
  }

  private static SignedInPerson person(OAuth2AuthenticationToken authentication) {
    return (SignedInPerson) authentication.getPrincipal();
  }

  /** The token the CSRF filter prepared for this request; reading it stores it in the session. */
  private static Mono<CsrfToken> csrfToken(ServerWebExchange exchange) {
    Mono<CsrfToken> token = exchange.getAttribute(CsrfToken.class.getName());
    return token == null
        ? Mono.error(new IllegalStateException("no CSRF token was prepared for the request"))
        : token;
  }

  private static Map<String, Object> signedIn(SignedInPerson person, CsrfToken csrf) {
    Map<String, Object> personView = new LinkedHashMap<>();
    personView.put("principalId", person.principalId().value());
    personView.put("displayName", person.displayName());
    Map<String, Object> csrfView = new LinkedHashMap<>();
    csrfView.put("headerName", csrf.getHeaderName());
    csrfView.put("token", csrf.getToken());
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("state", SIGNED_IN);
    body.put("person", personView);
    body.put("csrf", csrfView);
    return body;
  }

  private static ResponseEntity<Map<String, Object>> notStored(Map<String, Object> body) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body);
  }
}
