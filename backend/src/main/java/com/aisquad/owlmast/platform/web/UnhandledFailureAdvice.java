package com.aisquad.owlmast.platform.web;

import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.blocking.BlockingCapacityExceededException;
import com.aisquad.owlmast.platform.blocking.BlockingDeadlineExceededException;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.platform.persistence.IncompatibleScopeException;
import com.aisquad.owlmast.platform.persistence.ScopeBindingUnavailableException;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
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
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

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
 *   <li>the shared kernel's own failures ({@link #STATUS_BY_PLATFORM_FAILURE}), which carry no web
 *       type because {@code platform} code below the web layer raises them: an {@link
 *       OperationDeniedException} is a denial (403); a missing, incompatible or unbindable scope is
 *       a defect of the calling code and stays 500, stated here so that it is a decision and not a
 *       default; a refused or late bounded blocking call is load or a slow dependency, not a defect
 *       (503 when capacity is exhausted, 504 when the deadline passed).
 * </ol>
 *
 * <p>A status outside 4xx/5xx is not an error answer and becomes 500, without the headers that came
 * with it. To give another exception type its own status, implement {@link ErrorResponse}, annotate
 * it with {@link ResponseStatus} or write a more specific advice.
 *
 * <p>Spring Security's {@code AccessDeniedException} and {@code AuthenticationException} are not
 * answered here (OM-02.01): they are signalled again, so that they leave the handler and reach the
 * security filter chain, whose translation decides between 401 with the challenge and 403 ({@code
 * AccessDeniedException}), and {@link FilterFailureHandler}, which answers what the chain does not
 * ({@code AuthenticationException}). Until OM-02.01 this advice answered both by class name.
 */
@Slf4j
@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
class UnhandledFailureAdvice {

  /**
   * Failures raised by the shared kernel ({@code platform}), by exact class: every one is final.
   * The denial reason code and the operation name stay out of the response like everything else.
   */
  static final Map<Class<? extends Throwable>, HttpStatus> STATUS_BY_PLATFORM_FAILURE =
      Map.of(
          OperationDeniedException.class,
          HttpStatus.FORBIDDEN,
          MissingScopeException.class,
          HttpStatus.INTERNAL_SERVER_ERROR,
          IncompatibleScopeException.class,
          HttpStatus.INTERNAL_SERVER_ERROR,
          ScopeBindingUnavailableException.class,
          HttpStatus.INTERNAL_SERVER_ERROR,
          BlockingCapacityExceededException.class,
          HttpStatus.SERVICE_UNAVAILABLE,
          BlockingDeadlineExceededException.class,
          HttpStatus.GATEWAY_TIMEOUT);

  @ExceptionHandler(Throwable.class)
  Mono<ResponseEntity<ProblemDetail>> unhandled(Throwable failure, ServerWebExchange exchange) {
    if (failure instanceof AccessDeniedException || failure instanceof AuthenticationException) {
      return Mono.error(failure);
    }
    return Mono.just(answer(failure, exchange));
  }

  private static ResponseEntity<ProblemDetail> answer(
      Throwable failure, ServerWebExchange exchange) {
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
    return STATUS_BY_PLATFORM_FAILURE.get(failure.getClass());
  }
}
