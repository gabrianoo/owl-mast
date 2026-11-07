package com.aisquad.owlmast.testing;

import java.net.URI;
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
  private final String publishedIssuer;

  private StubIdentityProvider(DisposableServer server, String realm, String publishedIssuer) {
    this.server = server;
    this.realm = realm;
    this.publishedIssuer = publishedIssuer;
  }

  /** Starts a provider whose discovery document publishes its own issuer URL (the happy path). */
  public static StubIdentityProvider start(String realm) {
    return start(realm, null);
  }

  /**
   * Starts a provider whose discovery endpoint answers {@code status} (200 or 204) with no body: a
   * reachable endpoint that never publishes an issuer, which must not satisfy readiness.
   */
  public static StubIdentityProvider startEmpty(String realm, int status) {
    DisposableServer server =
        HttpServer.create()
            .port(0)
            .route(routes ->
                routes.get(
                    "/realms/" + realm + "/.well-known/openid-configuration",
                    (request, response) ->
                        response.status(status).header("Content-Type", "application/json").send()))
            .bindNow();
    return new StubIdentityProvider(server, realm, null);
  }

  /**
   * Starts a provider that publishes {@code publishedIssuer} instead of its own URL, to prove a
   * mismatched issuer is refused. {@code null} publishes the real URL.
   */
  public static StubIdentityProvider start(String realm, String publishedIssuer) {
    DisposableServer[] holder = new DisposableServer[1];
    String[] issuer = new String[1];
    holder[0] =
        HttpServer.create()
            .port(0)
            .route(routes ->
                routes.get(
                    "/realms/" + realm + "/.well-known/openid-configuration",
                    (request, response) ->
                        response
                            .header("Content-Type", "application/json")
                            .sendString(
                                reactor.core.publisher.Mono.just(
                                    "{\"issuer\":\""
                                        + (publishedIssuer != null ? publishedIssuer : issuer[0])
                                        + "\",\"authorization_endpoint\":\""
                                        + issuer[0]
                                        + "/protocol/openid-connect/auth\"}"))))
            .bindNow();
    issuer[0] = "http://localhost:" + holder[0].port() + "/realms/" + realm;
    return new StubIdentityProvider(holder[0], realm, publishedIssuer);
  }

  public String issuerUri() {
    return "http://localhost:" + server.port() + "/realms/" + realm;
  }

  public URI discoveryUri() {
    return URI.create(issuerUri() + "/.well-known/openid-configuration");
  }

  public String publishedIssuer() {
    return publishedIssuer != null ? publishedIssuer : issuerUri();
  }

  @Override
  public void close() {
    server.disposeNow();
  }
}
