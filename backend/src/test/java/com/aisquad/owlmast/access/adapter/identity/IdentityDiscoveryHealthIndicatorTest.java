package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.testing.StubIdentityProvider;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.Status;
import org.springframework.web.reactive.function.client.WebClient;

class IdentityDiscoveryHealthIndicatorTest {

  private static Health check(String configuredIssuer) {
    IdentityDiscoveryHealthIndicator indicator =
        new IdentityDiscoveryHealthIndicator(
            WebClient.create(), new IdentityProperties(configuredIssuer, true));
    return indicator.health().block(Duration.ofSeconds(10));
  }

  @Test
  void downWhenTheConfiguredIssuerHasATrailingSlashThePublishedOneLacks() {
    // OpenID Connect Discovery 4.3: the published issuer must be identical to the configured one.
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      Health health = check(provider.issuerUri() + "/");
      assertThat(health.getStatus()).isEqualTo(Status.DOWN);
      assertThat(health.getDetails())
          .containsEntry("reason", "published issuer differs from the configured issuer")
          .containsEntry("issuer", provider.issuerUri() + "/");
      // The document was fetched: only the discovery location drops the terminating slash.
      assertThat(provider.discoveryRequests()).isEqualTo(1);
    }
  }

  @Test
  void downWhenThePublishedIssuerHasATrailingSlashTheConfiguredOneLacks() {
    try (StubIdentityProvider provider =
        StubIdentityProvider.startPublishingTrailingSlash("owl-mast")) {
      Health health = check(provider.issuerUri());
      assertThat(health.getStatus()).isEqualTo(Status.DOWN);
      assertThat(health.getDetails())
          .containsEntry("reason", "published issuer differs from the configured issuer");
    }
  }

  @Test
  void upWhenBothIssuersCarryTheSameTrailingSlash() {
    try (StubIdentityProvider provider =
        StubIdentityProvider.startPublishingTrailingSlash("owl-mast")) {
      Health health = check(provider.publishedIssuer());
      assertThat(health.getStatus()).isEqualTo(Status.UP);
      assertThat(health.getDetails()).containsEntry("issuer", provider.issuerUri() + "/");
    }
  }

  @Test
  void oneDiscoveryRequestServesEveryEvaluationWithinTheCacheInterval() {
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(),
              new IdentityProperties(provider.issuerUri(), true),
              Duration.ofSeconds(30));
      for (int i = 0; i < 25; i++) {
        assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus())
            .isEqualTo(Status.UP);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(1);
    }
  }

  @Test
  void aDownResultIsCachedTooAndRefreshedAfterTheInterval() throws InterruptedException {
    try (StubIdentityProvider provider =
        StubIdentityProvider.start("owl-mast", "https://other.example/realms/owl-mast")) {
      Duration ttl = Duration.ofMillis(300);
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(), new IdentityProperties(provider.issuerUri(), true), ttl);
      for (int i = 0; i < 10; i++) {
        assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus())
            .isEqualTo(Status.DOWN);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(1);
      Thread.sleep(ttl.toMillis() * 3);
      assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus())
          .isEqualTo(Status.DOWN);
      assertThat(provider.discoveryRequests()).isEqualTo(2);
    }
  }

  @Test
  void theCacheIntervalIsShorterThanTheChartsReadinessProbePeriod() {
    // values.yaml backend.probes.readiness.periodSeconds is 10: each kubelet probe sees a result
    // no older than the interval, and never a stale one from the previous probe.
    assertThat(IdentityDiscoveryHealthIndicator.CACHE_TTL).isLessThan(Duration.ofSeconds(10));
    assertThat(IdentityDiscoveryHealthIndicator.CACHE_TTL).isPositive();
  }

  @Test
  void upWhenPublishedIssuerMatchesConfiguredIssuer() {
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      Health health = check(provider.issuerUri());
      assertThat(health.getStatus()).isEqualTo(Status.UP);
      assertThat(health.getDetails()).containsEntry("issuer", provider.issuerUri());
    }
  }

  @Test
  void downWhenPublishedIssuerDiffers() {
    try (StubIdentityProvider provider =
        StubIdentityProvider.start("owl-mast", "http://other.example/realms/owl-mast")) {
      Health health = check(provider.issuerUri());
      assertThat(health.getStatus()).isEqualTo(Status.DOWN);
      assertThat(health.getDetails())
          .containsEntry("reason", "published issuer differs from the configured issuer");
    }
  }

  @Test
  void downWhenRealmDoesNotExist() {
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      Health health = check(provider.issuerUri().replace("owl-mast", "missing"));
      assertThat(health.getStatus()).isEqualTo(Status.DOWN);
      assertThat(health.getDetails()).containsEntry("reason", "discovery document unavailable");
    }
  }

  @Test
  void downWhenDiscoveryAnswersEmptyOk() {
    try (StubIdentityProvider provider = StubIdentityProvider.startEmpty("owl-mast", 200)) {
      Health health = check(provider.issuerUri());
      assertThat(health).isNotNull();
      assertThat(health.getStatus()).isEqualTo(Status.DOWN);
      assertThat(health.getDetails()).containsEntry("reason", "discovery response has no body");
    }
  }

  @Test
  void downWhenDiscoveryAnswersNoContent() {
    try (StubIdentityProvider provider = StubIdentityProvider.startEmpty("owl-mast", 204)) {
      Health health = check(provider.issuerUri());
      assertThat(health).isNotNull();
      assertThat(health.getStatus()).isEqualTo(Status.DOWN);
      assertThat(health.getDetails()).containsEntry("reason", "discovery response has no body");
    }
  }

  @Test
  void downWhenIssuerIsUnreachable() {
    Health health = check("http://127.0.0.1:1/realms/owl-mast");
    assertThat(health.getStatus()).isEqualTo(Status.DOWN);
    assertThat(health.getDetails()).containsEntry("reason", "discovery document unavailable");
    assertThat(health.getDetails().values()).noneMatch(v -> v.toString().contains("Connection"));
  }
}
