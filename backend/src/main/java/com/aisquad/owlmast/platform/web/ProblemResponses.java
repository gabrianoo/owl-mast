package com.aisquad.owlmast.platform.web;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Consumer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.codec.HttpMessageWriter;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.reactive.result.view.ViewResolver;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * Writes the common error envelope (RFC 9457 problem details, {@code application/problem+json})
 * from places no controller advice reaches: web filters, the security filter chain and the handler
 * of failures raised before a controller runs. The body is the status, its standard title and the
 * request path; it never carries an exception, a reason or a detail. A caller may add extension
 * members (RFC 9457 section 3.2) of its own making; they are written at the top level of the body,
 * next to the status.
 */
public final class ProblemResponses {

  private final ServerResponse.Context context;

  public ProblemResponses(ServerCodecConfigurer codecs) {
    List<HttpMessageWriter<?>> writers = codecs.getWriters();
    this.context =
        new ServerResponse.Context() {
          @Override
          public List<HttpMessageWriter<?>> messageWriters() {
            return writers;
          }

          @Override
          public List<ViewResolver> viewResolvers() {
            return List.of();
          }
        };
  }

  public Mono<Void> write(ServerWebExchange exchange, HttpStatusCode status) {
    return write(exchange, status, headers -> {});
  }

  /** Answers with {@code status}; a response that was already committed is left as it is. */
  public Mono<Void> write(
      ServerWebExchange exchange, HttpStatusCode status, Consumer<HttpHeaders> headers) {
    return write(exchange, status, headers, Map.of());
  }

  /**
   * Answers with {@code status} and the extension members {@code extensions}, each a top-level
   * member of the body. The values are the caller's own: nothing received from another system
   * belongs here.
   */
  public Mono<Void> write(
      ServerWebExchange exchange,
      HttpStatusCode status,
      Consumer<HttpHeaders> headers,
      Map<String, Object> extensions) {
    if (exchange.getResponse().isCommitted()) {
      return Mono.empty();
    }
    ProblemDetail problem = ProblemDetail.forStatus(status);
    instance(exchange).ifPresent(problem::setInstance);
    extensions.forEach(problem::setProperty);
    return ServerResponse.status(status)
        .headers(headers)
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .bodyValue(problem)
        .flatMap(response -> response.writeTo(exchange, context));
  }

  private static Optional<URI> instance(ServerWebExchange exchange) {
    try {
      return Optional.of(URI.create(exchange.getRequest().getPath().value()));
    } catch (IllegalArgumentException unparsable) {
      return Optional.empty();
    }
  }
}
