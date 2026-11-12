package com.aisquad.owlmast.testing;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.UnaryOperator;
import reactor.core.publisher.Mono;
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
  private final UnaryOperator<String> published;
  private final AtomicInteger discoveryRequests;

  private StubIdentityProvider(
      DisposableServer server,
      String realm,
      UnaryOperator<String> published,
      AtomicInteger discoveryRequests) {
    this.server = server;
    this.realm = realm;
    this.published = published;
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
    return new StubIdentityProvider(server, realm, UnaryOperator.identity(), requests);
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
      String realm, UnaryOperator<String> published, Duration delay) {
    AtomicInteger requests = new AtomicInteger();
    String[] own = new String[1];
    DisposableServer server =
        HttpServer.create()
            .port(0)
            .route(routes ->
                routes.get(
                    "/realms/" + realm + "/.well-known/openid-configuration",
                    (request, response) -> {
                      requests.incrementAndGet();
                      return response
                          .header("Content-Type", "application/json")
                          .sendString(
                              Mono.just(
                                      "{\"issuer\":\""
                                          + published.apply(own[0])
                                          + "\",\"authorization_endpoint\":\""
                                          + own[0]
                                          + "/protocol/openid-connect/auth\"}")
                                  .delaySubscription(delay));
                    }))
            .bindNow();
    own[0] = "http://localhost:" + server.port() + "/realms/" + realm;
    return new StubIdentityProvider(server, realm, published, requests);
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
    return published.apply(issuerUri());
  }

  /** How many discovery requests this provider has answered. */
  public int discoveryRequests() {
    return discoveryRequests.get();
  }

  @Override
  public void close() {
    server.disposeNow();
  }
}
