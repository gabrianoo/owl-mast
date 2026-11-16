package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.adapter.identity.SignInProperties;
import com.aisquad.owlmast.platform.web.ProblemResponses;
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import lombok.RequiredArgsConstructor;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * How the backend answers when it is done with a sign-in step. A browser navigation (a request that
 * accepts {@code text/html}) is sent to the shell on the application origin, with the outcome in a
 * query parameter when sign-in did not complete; the shell shows the state. Any other caller gets
 * the status in the problem-details envelope. Neither form carries what the identity provider said.
 */
@RequiredArgsConstructor
final class SignInResponses {

  /** The challenge of every 401: the API accepts a session cookie or a bearer credential. */
  static final String CHALLENGE = "Bearer";

  /** The member of a session answer that carries the CSRF token. */
  static final String CSRF_MEMBER = "csrf";

  private final SignInProperties properties;
  private final ProblemResponses problems;

  Mono<Void> completed(ServerWebExchange exchange) {
    return redirect(exchange, HttpStatus.FOUND, properties.applicationUrl("/"));
  }

  /** Sign-in was refused or its answer could not be accepted: 401 for an API caller. */
  Mono<Void> refused(ServerWebExchange exchange) {
    return navigation(exchange)
        ? toShell(exchange, SessionPaths.OUTCOME_FAILED)
        : unauthorized(exchange);
  }

  /** The identity provider (or a store behind sign-in) could not do its part: 503. */
  Mono<Void> unavailable(ServerWebExchange exchange) {
    return navigation(exchange)
        ? toShell(exchange, SessionPaths.OUTCOME_UNAVAILABLE)
        : problems.write(exchange, HttpStatus.SERVICE_UNAVAILABLE);
  }

  /** An outage on a call that is not a sign-in step: always the status, never the shell. */
  Mono<Void> outage(ServerWebExchange exchange) {
    return problems.write(exchange, HttpStatus.SERVICE_UNAVAILABLE);
  }

  /**
   * The session read ({@code GET /api/session}) of a session that is kept while the identity
   * provider cannot be asked whether it still stands: the outage, with the session's CSRF token as
   * the extension member {@code csrf} ({@code headerName}, {@code token}). Sign-out is served
   * during the outage and needs that token; a shell that starts then has no other way to learn it,
   * and the member also tells it that a session is kept. Nothing about the person is in the answer.
   * A request for which the CSRF filter prepared no token gets the plain outage.
   */
  Mono<Void> sessionUnconfirmed(ServerWebExchange exchange) {
    Mono<CsrfToken> prepared = exchange.getAttribute(CsrfToken.class.getName());
    if (prepared == null) {
      return outage(exchange);
    }
    return prepared
        .map(Optional::of)
        .defaultIfEmpty(Optional.empty())
        .flatMap(csrf ->
            csrf.map(token ->
                    problems.write(
                        exchange,
                        HttpStatus.SERVICE_UNAVAILABLE,
                        headers -> headers.setCacheControl(CacheControl.noStore()),
                        Map.of(CSRF_MEMBER, csrfView(token))))
                .orElseGet(() -> outage(exchange)));
  }

  /** The CSRF token as the session answers publish it: the header to send and its value. */
  static Map<String, Object> csrfView(CsrfToken csrf) {
    Map<String, Object> view = new LinkedHashMap<>();
    view.put("headerName", csrf.getHeaderName());
    view.put("token", csrf.getToken());
    return view;
  }

  /** The browser already has a session: back to the shell, which shows it. */
  Mono<Void> alreadySignedIn(ServerWebExchange exchange) {
    return completed(exchange);
  }

  Mono<Void> unauthorized(ServerWebExchange exchange) {
    return unauthorized(exchange, CHALLENGE);
  }

  Mono<Void> unauthorized(ServerWebExchange exchange, String challenge) {
    return problems.write(
        exchange,
        HttpStatus.UNAUTHORIZED,
        headers -> headers.set(HttpHeaders.WWW_AUTHENTICATE, challenge));
  }

  Mono<Void> forbidden(ServerWebExchange exchange) {
    return problems.write(exchange, HttpStatus.FORBIDDEN);
  }

  private Mono<Void> toShell(ServerWebExchange exchange, String outcome) {
    return redirect(
        exchange,
        HttpStatus.SEE_OTHER,
        properties.applicationUrl("/?" + SessionPaths.OUTCOME_PARAMETER + "=" + outcome));
  }

  private static Mono<Void> redirect(ServerWebExchange exchange, HttpStatus status, String to) {
    if (exchange.getResponse().isCommitted()) {
      return Mono.empty();
    }
    exchange.getResponse().setStatusCode(status);
    exchange.getResponse().getHeaders().setLocation(URI.create(to));
    return exchange.getResponse().setComplete();
  }

  private static boolean navigation(ServerWebExchange exchange) {
    try {
      return exchange.getRequest().getHeaders().getAccept().stream()
          .anyMatch(accepted ->
              !accepted.isWildcardType() && accepted.isCompatibleWith(MediaType.TEXT_HTML));
    } catch (IllegalArgumentException unparsableAccept) {
      return false;
    }
  }
}
