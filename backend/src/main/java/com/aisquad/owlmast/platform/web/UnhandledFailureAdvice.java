package com.aisquad.owlmast.platform.web;

import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

/**
 * Common error envelope for failures no handler claimed (OM-01.04): anything thrown or signalled by
 * a controller, an {@link Error} included, becomes an RFC 9457 problem detail with status 500 and
 * nothing else.
 *
 * <p>{@code spring.webflux.problemdetails.enabled} only covers Spring's own {@code ErrorResponse}
 * exceptions (404, 405, 415, validation). Anything else used to reach Boot's default error handler,
 * whose body is {@code application/json} error attributes rather than {@code
 * application/problem+json}. This advice runs last, so the framework's handler still answers every
 * exception it knows, and a feature's own, more specific advice wins.
 *
 * <p>The response never carries the exception: no message, class name, cause or trace. The log line
 * names the exception classes only ({@link SafeFailure}), prefixed with the exchange's request id
 * so it can be matched to the request; driver and SDK messages can hold connection strings and
 * payload fragments, and paths can hold protected identifiers.
 *
 * <p>{@code Throwable}, not {@code Exception}: an {@code AssertionError} from a handler is answered
 * either way (Boot's default handler would answer it and the server would carry on), so the only
 * choice here is the envelope, and it is the same one. Not covered: an error Reactor treats as
 * fatal when an operator raises it ({@code VirtualMachineError}, {@code LinkageError}) is rethrown
 * instead of signalled and reaches no handler.
 *
 * <p>A story that adds exceptions with their own status (authentication and authorization, E02)
 * must map them in a more specific advice: left to this one they would answer 500, not 401/403.
 */
@Slf4j
@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
class UnhandledFailureAdvice {

  @ExceptionHandler(Throwable.class)
  ProblemDetail unhandled(Throwable failure, ServerWebExchange exchange) {
    log.error(
        "{}Unhandled request failure: {}", exchange.getLogPrefix(), SafeFailure.describe(failure));
    return ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
  }
}
