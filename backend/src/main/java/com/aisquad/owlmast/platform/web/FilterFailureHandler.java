package com.aisquad.owlmast.platform.web;

import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;
import reactor.core.publisher.Mono;

/**
 * The common error envelope for failures raised outside a controller (OM-02.01): a web filter, the
 * security filter chain, or an exception a controller advice signalled again. Before this handler
 * such a failure got Spring Boot's default error body ({@code application/json} error attributes);
 * it runs before that handler and answers everything, so that body is no longer produced.
 *
 * <p>The status is the one the failure carries, as in {@link UnhandledFailureAdvice}, with two
 * additions for failures that advice hands on: an {@code AuthenticationException} is 401 with the
 * {@code WWW-Authenticate} challenge, except {@code AuthenticationServiceException}, which is the
 * identity provider or a store failing and stays 500; an {@code AccessDeniedException} that the
 * security chain did not translate is 403. The response carries no message, class name or cause;
 * the log names the exception classes only.
 */
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@Slf4j
@Component
@Order(-2)
@RequiredArgsConstructor
final class FilterFailureHandler implements WebExceptionHandler {

  /** The challenge of every 401: the API accepts a session cookie or a bearer credential. */
  static final String CHALLENGE = "Bearer";

  private final ProblemResponses problems;

  @Override
  public Mono<Void> handle(ServerWebExchange exchange, Throwable failure) {
    if (exchange.getResponse().isCommitted()) {
      return Mono.error(failure);
    }
    HttpStatusCode status = statusOf(failure);
    if (status.is5xxServerError()) {
      log.error(
          "{}Unhandled request failure: {}",
          exchange.getLogPrefix(),
          SafeFailure.describe(failure));
    } else {
      log.debug(
          "{}Request failure answered {}: {}",
          exchange.getLogPrefix(),
          status.value(),
          SafeFailure.describe(failure));
    }
    return problems.write(
        exchange,
        status,
        headers -> {
          if (status.value() == HttpStatus.UNAUTHORIZED.value()) {
            headers.set(HttpHeaders.WWW_AUTHENTICATE, CHALLENGE);
          }
        });
  }

  static HttpStatusCode statusOf(Throwable failure) {
    if (failure instanceof AuthenticationServiceException) {
      return HttpStatus.INTERNAL_SERVER_ERROR;
    }
    if (failure instanceof AuthenticationException) {
      return HttpStatus.UNAUTHORIZED;
    }
    if (failure instanceof AccessDeniedException) {
      return HttpStatus.FORBIDDEN;
    }
    return UnhandledFailureAdvice.statusOf(failure);
  }
}
