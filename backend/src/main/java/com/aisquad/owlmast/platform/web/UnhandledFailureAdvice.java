package com.aisquad.owlmast.platform.web;

import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.util.Map;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

/**
 * Common error envelope for failures no handler claimed (OM-01.04): anything thrown or signalled by
 * a controller, an {@link Error} included, becomes an RFC 9457 problem detail with a status and
 * nothing else. The status is 500 unless the failure carries its own (see below).
 *
 * <p>{@code spring.webflux.problemdetails.enabled} only covers Spring's own {@code ErrorResponse}
 * exceptions (404, 405, 415, validation). Anything else used to reach Boot's default error handler,
 * whose body is {@code application/json} error attributes rather than {@code
 * application/problem+json}. This advice runs last, so the framework's handler still answers every
 * exception it knows, and a feature's own, more specific advice wins.
 *
 * <p>The response never carries the exception: no message, class name, cause, reason or trace. The
 * log line names the exception classes only ({@link SafeFailure}), prefixed with the exchange's
 * request id so it can be matched to the request; driver and SDK messages can hold connection
 * strings and payload fragments, and paths can hold protected identifiers.
 *
 * <p>{@code Throwable}, not {@code Exception}: an {@code AssertionError} from a handler is answered
 * either way (Boot's default handler would answer it and the server would carry on), so the only
 * choice here is the envelope, and it is the same one. Not covered: an error Reactor treats as
 * fatal when an operator raises it ({@code VirtualMachineError}, {@code LinkageError}) is rethrown
 * instead of signalled and reaches no handler.
 *
 * <p>A failure that carries its own status keeps it, because catching everything must not turn a
 * denial into a server error (the shell shows its denied state for 401/403 and a problem state for
 * 500). Looked at in this order, on the failure itself and not on its causes:
 *
 * <ol>
 *   <li>an {@link ErrorResponse} (the framework's handler answers {@code ResponseStatusException}
 *       and {@code ErrorResponseException} before this advice; any other implementation arrives
 *       here): its status and headers;
 *   <li>a class annotated with {@link ResponseStatus}: the annotated code, without the reason;
 *   <li>Spring Security's {@code AccessDeniedException} (403) and {@code AuthenticationException}
 *       (401), or a subclass, recognised by class name ({@link #STATUS_BY_CLASS_NAME}) because
 *       Spring Security is not a dependency yet. The nearest listed class wins, so {@code
 *       AuthenticationServiceException} and its subclasses stay 500: the identity provider or user
 *       store failed, which is an outage and not a credential problem.
 * </ol>
 *
 * <p>A status outside 4xx/5xx is not an error answer and becomes 500, without the headers that came
 * with it. The name guard is a floor for E02, not its design. A controller advice answers before
 * the failure reaches a web filter, so while the guard exists Spring Security's own translation
 * (its entry point, the {@code WWW-Authenticate} challenge, 401 instead of 403 for an anonymous
 * caller) never sees these exceptions: the story that adds authentication must remove the two names
 * or replace them with its own advice. To give another exception type its own status, implement
 * {@link ErrorResponse}, annotate it with {@link ResponseStatus} or write a more specific advice;
 * extend the name table only for types of a library that is not on the classpath.
 */
@Slf4j
@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
class UnhandledFailureAdvice {

  /**
   * Exception types of libraries this module does not depend on, by fully qualified class name,
   * matched against the failure's class and its superclasses.
   */
  static final Map<String, HttpStatus> STATUS_BY_CLASS_NAME =
      Map.of(
          "org.springframework.security.access.AccessDeniedException",
          HttpStatus.FORBIDDEN,
          "org.springframework.security.core.AuthenticationException",
          HttpStatus.UNAUTHORIZED,
          "org.springframework.security.authentication.AuthenticationServiceException",
          HttpStatus.INTERNAL_SERVER_ERROR);

  @ExceptionHandler(Throwable.class)
  ResponseEntity<ProblemDetail> unhandled(Throwable failure, ServerWebExchange exchange) {
    HttpStatusCode carried = carriedStatus(failure);
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
    // Headers belong to the status they came with: not to a 500 that replaced it.
    HttpHeaders headers =
        failure instanceof ErrorResponse response && status.equals(carried)
            ? response.getHeaders()
            : HttpHeaders.EMPTY;
    return ResponseEntity.status(status).headers(headers).body(ProblemDetail.forStatus(status));
  }

  /** The status the failure carries itself, or 500. */
  static HttpStatusCode statusOf(Throwable failure) {
    HttpStatusCode carried = carriedStatus(failure);
    return carried != null && carried.isError() ? carried : HttpStatus.INTERNAL_SERVER_ERROR;
  }

  private static HttpStatusCode carriedStatus(Throwable failure) {
    if (failure instanceof ErrorResponse response) {
      return response.getStatusCode();
    }
    ResponseStatus annotation =
        AnnotatedElementUtils.findMergedAnnotation(failure.getClass(), ResponseStatus.class);
    if (annotation != null) {
      return annotation.code();
    }
    for (Class<?> type = failure.getClass(); type != null; type = type.getSuperclass()) {
      HttpStatus byName = STATUS_BY_CLASS_NAME.get(type.getName());
      if (byName != null) {
        return byName;
      }
    }
    return null;
  }
}
