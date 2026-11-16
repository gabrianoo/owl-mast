package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

/**
 * What the backend accepts as the issuer's endpoints, against a local server that publishes
 * whatever document a test gives it.
 */
class IdentityDiscoveryTest {

  private final AtomicReference<String> document = new AtomicReference<>("{}");
  private final AtomicInteger requests = new AtomicInteger();

  /** Answers wait for this; a test replaces it to hold them. */
  private final AtomicReference<Mono<Void>> gate = new AtomicReference<>(Mono.empty());

  private final DisposableServer server =
      HttpServer.create()
          .port(0)
          .route(routes ->
              routes.get(
                  "/realms/owl-mast/.well-known/openid-configuration",
                  (request, response) -> {
                    requests.incrementAndGet();
                    return response
                        .header("Content-Type", "application/json")
                        .sendString(
                            Mono.fromSupplier(document::get)
                                .delaySubscription(Mono.defer(gate::get)));
                  }))
          .bindNow();
  private final String address = "http://localhost:" + server.port() + "/realms/owl-mast";

  @AfterEach
  void stop() {
    server.disposeNow();
  }

  @Test
  void theEndpointsOfAMatchingDocumentAreUsedAndKept() {
    publish(
        address, address + "/auth", address + "/protocol/openid-connect/token", address + "/certs");
    IdentityDiscovery discovery =
        new IdentityDiscovery(WebClient.create(), new IdentityProperties(address, true));

    StepVerifier.create(discovery.metadata())
        .assertNext(metadata -> {
          assertThat(metadata.issuer()).isEqualTo(address);
          assertThat(metadata.authorizationEndpoint()).isEqualTo(address + "/auth");
          assertThat(metadata.tokenEndpoint())
              .isEqualTo(address + "/protocol/openid-connect/token");
          assertThat(metadata.jwksUri()).isEqualTo(address + "/certs");
          assertThat(metadata.logoutEndpoint())
              .contains(address + "/protocol/openid-connect/logout");
        })
        .verifyComplete();
    StepVerifier.create(discovery.metadata()).expectNextCount(1).verifyComplete();
    assertThat(requests).hasValue(1);
  }

  /** The bundled Keycloak: the issuer is its public origin, the document comes from the cluster. */
  @Test
  void aPublicIssuerIsReadThroughTheBackchannelAddress() {
    String publicIssuer = "https://id.example/realms/owl-mast";
    publish(publicIssuer, publicIssuer + "/auth", address + "/token", address + "/certs");
    IdentityDiscovery discovery =
        new IdentityDiscovery(
            WebClient.create(), new IdentityProperties(publicIssuer, false, address, true));

    StepVerifier.create(discovery.metadata())
        .assertNext(metadata -> {
          assertThat(metadata.issuer()).isEqualTo(publicIssuer);
          assertThat(metadata.authorizationEndpoint()).isEqualTo(publicIssuer + "/auth");
          assertThat(metadata.tokenEndpoint()).isEqualTo(address + "/token");
          // Not Keycloak's layout: no logout endpoint is derived.
          assertThat(metadata.logoutEndpoint()).isEmpty();
        })
        .verifyComplete();
  }

  @Test
  void aDocumentOfAnotherIssuerOrWithoutEndpointsIsAnOutageAndIsAskedForAgain() {
    // No retry interval here, so every call reads again.
    IdentityDiscovery discovery =
        new IdentityDiscovery(
            WebClient.create(),
            new IdentityProperties(address, true),
            IdentityDiscovery.KEPT,
            Duration.ZERO);

    publish(address + "/", address + "/auth", address + "/token", address + "/certs");
    StepVerifier.create(discovery.metadata())
        .expectError(IdentityProviderUnavailableException.class)
        .verify();
    document.set(
        "{\"issuer\":\"" + address + "\",\"authorization_endpoint\":\"" + address + "/a\"}");
    StepVerifier.create(discovery.metadata())
        .expectError(IdentityProviderUnavailableException.class)
        .verify();
    publish(address, "javascript:alert(1)", address + "/token", address + "/certs");
    StepVerifier.create(discovery.metadata())
        .expectError(IdentityProviderUnavailableException.class)
        .verify();
    // Once the provider is right, the next read gets its endpoints.
    publish(address, address + "/auth", address + "/token", address + "/certs");
    StepVerifier.create(discovery.metadata()).expectNextCount(1).verifyComplete();
    assertThat(requests).hasValue(4);
  }

  /**
   * R2-1: anybody can cause a read by presenting a credential. While no document was accepted, the
   * failure is kept for the retry interval, so the provider receives one discovery request per
   * interval however many callers arrive. Before, every caller sent its own.
   */
  @Test
  void beforeADocumentWasAcceptedAFailingProviderIsAskedOncePerRetryInterval() {
    VirtualTimeScheduler time = VirtualTimeScheduler.create();
    IdentityDiscovery discovery =
        new IdentityDiscovery(
            WebClient.create(),
            new IdentityProperties(address, true),
            IdentityDiscovery.KEPT,
            IdentityDiscovery.RETRY,
            time);

    for (int i = 0; i < 50; i++) {
      assertUnavailable(discovery);
    }
    assertThat(requests).hasValue(1);

    time.advanceTimeBy(IdentityDiscovery.RETRY.minusMillis(1));
    assertUnavailable(discovery);
    assertThat(requests).hasValue(1);

    // The interval has passed: one more read, which again answers every caller after it.
    time.advanceTimeBy(Duration.ofMillis(1));
    for (int i = 0; i < 50; i++) {
      assertUnavailable(discovery);
    }
    assertThat(requests).hasValue(2);

    // The provider is right at the next read, and the document is then kept as an accepted one.
    time.advanceTimeBy(IdentityDiscovery.RETRY);
    publish(address, address + "/auth", address + "/token", address + "/certs");
    for (int i = 0; i < 50; i++) {
      StepVerifier.create(discovery.metadata()).expectNextCount(1).verifyComplete();
    }
    assertThat(requests).hasValue(3);
  }

  /** R2-1: callers that arrive together before any acceptance share the one read in flight. */
  @Test
  void callersArrivingWhileAReadIsUnansweredBeforeAnyAcceptanceShareIt() throws Exception {
    Sinks.Empty<Void> held = Sinks.empty();
    gate.set(held.asMono());
    IdentityDiscovery discovery = onClock(VirtualTimeScheduler.create());

    List<CompletableFuture<ProviderMetadata>> waiting = new ArrayList<>();
    for (int i = 0; i < 10; i++) {
      waiting.add(discovery.metadata().toFuture());
    }
    awaitRequests(1);
    assertThat(waiting).noneMatch(CompletableFuture::isDone);

    held.tryEmitEmpty();
    for (CompletableFuture<ProviderMetadata> answer : waiting) {
      assertThatThrownBy(() -> answer.get(30, TimeUnit.SECONDS))
          .hasCauseInstanceOf(IdentityProviderUnavailableException.class);
    }
    assertThat(requests).hasValue(1);
  }

  /** The time the provider is given runs on the timer: the test moves the clock to it. */
  @Test
  void aDiscoveryEndpointThatNeverAnswersIsAnOutageWhenItsTimeHasPassed() throws Exception {
    gate.set(Mono.never());
    VirtualTimeScheduler time = VirtualTimeScheduler.create();
    IdentityDiscovery discovery = onClock(time);

    CompletableFuture<ProviderMetadata> waiting = discovery.metadata().toFuture();
    awaitRequests(1);
    time.advanceTimeBy(IdentityDiscovery.TIMEOUT.minusMillis(1));
    assertThat(waiting).isNotDone();
    time.advanceTimeBy(Duration.ofMillis(1));

    // Given up by the move of the clock itself, not by real time passing.
    assertThat(waiting).isDone();
    assertThatThrownBy(() -> waiting.get(30, TimeUnit.SECONDS))
        .hasCauseInstanceOf(IdentityProviderUnavailableException.class);
  }

  private IdentityDiscovery onClock(VirtualTimeScheduler time) {
    return new IdentityDiscovery(
        WebClient.create(),
        new IdentityProperties(address, true),
        IdentityDiscovery.KEPT,
        IdentityDiscovery.RETRY,
        time);
  }

  /** Waits (real time, bounded) until the provider has received {@code count} requests. */
  private void awaitRequests(int count) throws InterruptedException {
    long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
    while (requests.get() < count && System.nanoTime() < deadline) {
      Thread.sleep(5);
    }
    assertThat(requests).hasValue(count);
  }

  private static void assertUnavailable(IdentityDiscovery discovery) {
    StepVerifier.create(discovery.metadata())
        .expectError(IdentityProviderUnavailableException.class)
        .verify(Duration.ofSeconds(30));
  }

  /** A provider that is briefly away or wrong must not turn valid sessions into outages. */
  @Test
  void theLastAcceptedDocumentIsUsedWhileAReadFails() {
    publish(address, address + "/auth", address + "/token", address + "/certs");
    // Nothing is kept between calls here, so every call reads again.
    IdentityDiscovery discovery =
        new IdentityDiscovery(
            WebClient.create(),
            new IdentityProperties(address, true),
            Duration.ZERO,
            Duration.ZERO);
    StepVerifier.create(discovery.metadata()).expectNextCount(1).verifyComplete();

    document.set("{}");
    StepVerifier.create(discovery.metadata())
        .assertNext(metadata -> assertThat(metadata.tokenEndpoint()).isEqualTo(address + "/token"))
        .verifyComplete();
    // PR #194 review, R3-3: a document this class refuses is treated like a read that failed,
    // whatever it is refused for: another issuer, or an endpoint that is not http(s).
    publish("https://other.example/realms/x", address + "/auth", address + "/token2", address);
    StepVerifier.create(discovery.metadata())
        .assertNext(metadata -> assertThat(metadata.tokenEndpoint()).isEqualTo(address + "/token"))
        .verifyComplete();
    publish(address, address + "/auth", "ftp://id.example/token", address + "/certs");
    StepVerifier.create(discovery.metadata())
        .assertNext(metadata -> assertThat(metadata.tokenEndpoint()).isEqualTo(address + "/token"))
        .verifyComplete();
    server.disposeNow();
    StepVerifier.create(discovery.metadata())
        .assertNext(metadata -> assertThat(metadata.tokenEndpoint()).isEqualTo(address + "/token"))
        .verifyComplete();
    assertThat(requests).hasValue(4);
  }

  /** A read that failed is tried again after the retry interval, not after the kept interval. */
  @Test
  void aFailedReadIsRetriedSoonAndANewDocumentReplacesTheEarlierOne() {
    publish(address, address + "/auth", address + "/token", address + "/certs");
    IdentityDiscovery discovery =
        new IdentityDiscovery(
            WebClient.create(),
            new IdentityProperties(address, true),
            Duration.ZERO,
            Duration.ofHours(1));
    StepVerifier.create(discovery.metadata()).expectNextCount(1).verifyComplete();

    document.set("{}");
    StepVerifier.create(discovery.metadata()).expectNextCount(1).verifyComplete();
    // Within the retry interval the provider is not asked again.
    publish(address, address + "/auth", address + "/token2", address + "/certs");
    StepVerifier.create(discovery.metadata())
        .assertNext(metadata -> assertThat(metadata.tokenEndpoint()).isEqualTo(address + "/token"))
        .verifyComplete();
    assertThat(requests).hasValue(2);
  }

  /** An https issuer must not hand the browser or the backend a plaintext endpoint. */
  @Test
  void aPlaintextEndpointIsRefusedWhereThePlaintextAddressWasNotAllowed() {
    String publicIssuer = "https://id.example/realms/owl-mast";
    IdentityDiscovery discovery =
        new IdentityDiscovery(
            WebClient.create(), new IdentityProperties(publicIssuer, false, address, true));

    publish(publicIssuer, "http://id.example/auth", address + "/token", address + "/certs");
    StepVerifier.create(discovery.metadata())
        .expectError(IdentityProviderUnavailableException.class)
        .verify();
  }

  @Test
  void anUnreachableProviderIsAnOutageWithoutItsDetail() {
    server.disposeNow();
    IdentityDiscovery discovery =
        new IdentityDiscovery(WebClient.create(), new IdentityProperties(address, true));

    StepVerifier.create(discovery.metadata())
        .expectErrorSatisfies(failure ->
            assertThat(failure)
                .isInstanceOf(IdentityProviderUnavailableException.class)
                .hasMessage("The identity provider is unavailable"))
        .verify();
  }

  @Test
  void theBackchannelAddressFollowsTheIssuersRulesWithItsOwnOptIn() {
    assertThatThrownBy(() ->
            new IdentityProperties(
                "https://id.example/realms/x", false, "http://keycloak:8080/realms/x", false))
        .hasMessageContaining("owlmast.identity.backchannel-uri must use https")
        .hasMessageContaining("owlmast.identity.allow-insecure-backchannel");
    assertThatThrownBy(() ->
            new IdentityProperties(
                "https://id.example/realms/x", false, "https://keycloak/realms/x?a=b", false))
        .hasMessageContaining("owlmast.identity.backchannel-uri must not contain a query");
    IdentityProperties bundled =
        new IdentityProperties(
            "https://id.example/realms/x", false, "http://keycloak:8080/realms/x/", true);
    assertThat(bundled.discoveryUri())
        .hasToString("http://keycloak:8080/realms/x/.well-known/openid-configuration");
    // Absent or blank means the issuer itself.
    assertThat(
            new IdentityProperties("https://id.example/realms/x", false, " ", false).discoveryUri())
        .hasToString("https://id.example/realms/x/.well-known/openid-configuration");
  }

  private void publish(String issuer, String authorization, String token, String keys) {
    document.set(
        "{\"issuer\":\""
            + issuer
            + "\",\"authorization_endpoint\":\""
            + authorization
            + "\",\"token_endpoint\":\""
            + token
            + "\",\"jwks_uri\":\""
            + keys
            + "\"}");
  }
}
