package com.aisquad.owlmast.platform.web;

import java.net.URI;
import java.util.List;
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
 * request path; it never carries an exception, a reason or a detail.
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
    if (exchange.getResponse().isCommitted()) {
      return Mono.empty();
    }
    ProblemDetail problem = ProblemDetail.forStatus(status);
    instance(exchange).ifPresent(problem::setInstance);
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
