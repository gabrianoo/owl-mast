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
            WebClient.create(), new IdentityProperties(configuredIssuer));
    return indicator.health().block(Duration.ofSeconds(10));
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
  void downWhenIssuerIsUnreachable() {
    Health health = check("http://127.0.0.1:1/realms/owl-mast");
    assertThat(health.getStatus()).isEqualTo(Status.DOWN);
    assertThat(health.getDetails()).containsEntry("reason", "discovery document unavailable");
    assertThat(health.getDetails().values()).noneMatch(v -> v.toString().contains("Connection"));
  }
}
