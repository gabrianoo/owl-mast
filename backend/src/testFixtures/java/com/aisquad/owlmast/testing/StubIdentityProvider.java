package com.aisquad.owlmast.testing;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.UnaryOperator;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

/**
 * Minimal OpenID Connect discovery endpoint for tests: publishes a discovery document for one
 * realm. It stands in for the issuer's network contract only; it is not a Keycloak substitute and
 * proves nothing about realm, client or session policy (OM-02.01).
 */
public final class StubIdentityProvider implements AutoCloseable {

  private final DisposableServer server;
  private final String realm;
  private final AtomicReference<UnaryOperator<String>> published;
  private final AtomicReference<Mono<Void>> gate;
  private final AtomicReference<Sinks.Empty<Void>> held = new AtomicReference<>();
  private final AtomicInteger discoveryRequests;

  private StubIdentityProvider(
      DisposableServer server,
      String realm,
      AtomicReference<UnaryOperator<String>> published,
      AtomicReference<Mono<Void>> gate,
      AtomicInteger discoveryRequests) {
    this.server = server;
    this.realm = realm;
    this.published = published;
    this.gate = gate;
    this.discoveryRequests = discoveryRequests;
  }

  /** Starts a provider whose discovery document publishes its own issuer URL (the happy path). */
  public static StubIdentityProvider start(String realm) {
    return start(realm, UnaryOperator.identity());
  }

  /**
   * Starts a provider that publishes {@code publishedIssuer} instead of its own URL, to prove a
   * mismatched issuer is refused. {@code null} publishes the real URL.
   */
  public static StubIdentityProvider start(String realm, String publishedIssuer) {
    return start(realm, own -> publishedIssuer != null ? publishedIssuer : own);
  }

  /**
   * Starts a provider that publishes its own URL with a terminating slash, as some providers do.
   * The discovery document is still served below the slash-less URL.
   */
  public static StubIdentityProvider startPublishingTrailingSlash(String realm) {
    return start(realm, own -> own + "/");
  }

  /**
   * Starts a provider whose discovery endpoint answers {@code status} (200 or 204) with no body: a
   * reachable endpoint that never publishes an issuer, which must not satisfy readiness.
   */
  public static StubIdentityProvider startEmpty(String realm, int status) {
    AtomicInteger requests = new AtomicInteger();
    DisposableServer server =
        HttpServer.create()
            .port(0)
            .route(routes ->
                routes.get(
                    "/realms/" + realm + "/.well-known/openid-configuration",
                    (request, response) -> {
                      requests.incrementAndGet();
                      return response
                          .status(status)
                          .header("Content-Type", "application/json")
                          .send();
                    }))
            .bindNow();
    return new StubIdentityProvider(
        server,
        realm,
        new AtomicReference<>(UnaryOperator.identity()),
        new AtomicReference<>(Mono.empty()),
        requests);
  }

  /**
   * Starts a happy-path provider that answers every discovery request only after {@code delay}, to
   * prove how a slow answer is aged by a cache.
   */
  public static StubIdentityProvider startSlow(String realm, Duration delay) {
    return start(realm, UnaryOperator.identity(), delay);
  }

  private static StubIdentityProvider start(String realm, UnaryOperator<String> published) {
    return start(realm, published, Duration.ZERO);
  }

  private static StubIdentityProvider start(
      String realm, UnaryOperator<String> initiallyPublished, Duration delay) {
    AtomicInteger requests = new AtomicInteger();
    AtomicReference<UnaryOperator<String>> published = new AtomicReference<>(initiallyPublished);
    AtomicReference<Mono<Void>> gate = new AtomicReference<>(Mono.empty());
    String[] own = new String[1];
    DisposableServer server =
        HttpServer.create()
            .port(0)
            .route(routes ->
                routes.get(
                    "/realms/" + realm + "/.well-known/openid-configuration",
                    (request, response) -> {
                      requests.incrementAndGet();
                      // The document is written when the answer is sent, not when the request
                      // arrived: a held answer publishes the value current at its release.
                      return response
                          .header("Content-Type", "application/json")
                          .sendString(
                              Mono.fromSupplier(() ->
                                      "{\"issuer\":\""
                                          + published.get().apply(own[0])
                                          + "\",\"authorization_endpoint\":\""
                                          + own[0]
                                          + "/protocol/openid-connect/auth\"}")
                                  .delaySubscription(delay)
                                  .delaySubscription(Mono.defer(gate::get)));
                    }))
            .bindNow();
    own[0] = "http://localhost:" + server.port() + "/realms/" + realm;
    return new StubIdentityProvider(server, realm, published, gate, requests);
  }

  /**
   * Changes the issuer the discovery document publishes from the next answer on, while the provider
   * keeps running: a provider whose configuration is corrected, or broken, under a running backend.
   * {@code null} publishes the provider's own URL again (the matching issuer).
   */
  public void publish(String publishedIssuer) {
    published.set(own -> publishedIssuer != null ? publishedIssuer : own);
  }

  /**
   * Holds every discovery answer from now on: requests are received and counted, and answered only
   * when {@link #releaseAnswers()} is called. A test decides how long an answer takes without
   * waiting for a real delay.
   */
  public void holdAnswers() {
    Sinks.Empty<Void> sink = Sinks.empty();
    held.set(sink);
    gate.set(sink.asMono());
  }

  /** Answers the held requests and stops holding new ones. */
  public void releaseAnswers() {
    gate.set(Mono.empty());
    Sinks.Empty<Void> sink = held.getAndSet(null);
    if (sink != null) {
      sink.tryEmitEmpty();
    }
  }

  /** The provider's own URL, without a terminating slash. */
  public String issuerUri() {
    return "http://localhost:" + server.port() + "/realms/" + realm;
  }

  public URI discoveryUri() {
    return URI.create(issuerUri() + "/.well-known/openid-configuration");
  }

  /** The issuer the discovery document publishes. */
  public String publishedIssuer() {
    return published.get().apply(issuerUri());
  }

  /** How many discovery requests this provider has received (answered or still held). */
  public int discoveryRequests() {
    return discoveryRequests.get();
  }

  @Override
  public void close() {
    server.disposeNow();
  }
}
