package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.testing.StubIdentityProvider;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.Status;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.web.reactive.function.client.WebClient;

@ExtendWith(OutputCaptureExtension.class)
class IdentityDiscoveryHealthIndicatorTest {

  private static final String MISMATCH_WARNING = "Identity discovery: the published issuer [";

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
          .containsEntry("issuer", provider.issuerUri() + "/")
          // The value the provider published, so a difference of one slash can be corrected.
          .containsEntry("publishedIssuer", provider.issuerUri());
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
  void theCacheIntervalIsShorterThanTheChartsDefaultReadinessProbePeriod() {
    // values.yaml backend.probes.readiness.periodSeconds defaults to 10. The binding rule lives in
    // the chart, which refuses a period that is not greater than CACHE_TTL; the render test
    // test_readiness_period_is_longer_than_the_backends_cache_interval reads the constant from
    // the source file, so the two cannot drift apart. The rule is sufficient because the interval
    // is counted from the start of the request (see the test below on a slow provider).
    assertThat(IdentityDiscoveryHealthIndicator.CACHE_TTL).isLessThan(Duration.ofSeconds(10));
    assertThat(IdentityDiscoveryHealthIndicator.CACHE_TTL).isPositive();
  }

  @Test
  void theProductionConstructorCachesForTheDocumentedInterval() {
    // The two-argument constructor is the one IdentityConfiguration uses: several evaluations
    // within CACHE_TTL must cost the provider one request.
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(), new IdentityProperties(provider.issuerUri(), true));
      for (int i = 0; i < 20; i++) {
        assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus())
            .isEqualTo(Status.UP);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(1);
    }
  }

  @Test
  void theConfiguredBeanCachesToo() {
    // The bean as the application wires it (IdentityConfiguration), not a hand-built instance.
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      new ApplicationContextRunner()
          .withUserConfiguration(IdentityConfiguration.class)
          .withPropertyValues(
              "owlmast.identity.issuer-uri=" + provider.issuerUri(),
              "owlmast.identity.allow-insecure-issuer=true")
          .run(context -> {
            assertThat(context).hasNotFailed();
            IdentityDiscoveryHealthIndicator indicator =
                context.getBean("identityDiscovery", IdentityDiscoveryHealthIndicator.class);
            for (int i = 0; i < 20; i++) {
              assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus())
                  .isEqualTo(Status.UP);
            }
            assertThat(provider.discoveryRequests()).isEqualTo(1);
          });
    }
  }

  @Test
  void aPublishedIssuerIsReportedBoundedAndPrintable(CapturedOutput output) {
    // JSON escapes, as the stub splices the text into the document: CR, LF and BEL once parsed.
    String hostile =
        "https://other.example/realms/x\\r\\nforged log line \\u0007" + "a".repeat(400);
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast", hostile)) {
      Health health = check(provider.issuerUri());
      assertThat(health.getStatus()).isEqualTo(Status.DOWN);
      String reported = (String) health.getDetails().get("publishedIssuer");
      assertThat(reported)
          .startsWith("https://other.example/realms/x??forged?log?line??aaa")
          .endsWith("...")
          .hasSize(IdentityDiscoveryHealthIndicator.MAX_REPORTED_ISSUER_LENGTH + 3)
          .matches("[\\x21-\\x7E]+");
      // The warning is the operator's only channel (the readiness details are not shown over
      // HTTP): it carries the cleaned value, and the remote text never starts a line of its own.
      String configured = provider.issuerUri();
      assertThat(output.getAll())
          .contains(
              MISMATCH_WARNING
                  + reported
                  + "] differs from the configured issuer ["
                  + configured
                  + "]")
          .contains("[https://other.example/realms/x??forged?log?line??aaa");
      assertThat(output.getAll().lines())
          .noneMatch(line -> line.startsWith("forged log line"))
          .noneMatch(line -> line.contains("\u0007"));
      assertThat(output.getAll().lines().filter(line -> line.contains("forged"))).hasSize(1);
    }
  }

  @Test
  void theMismatchWarningIsLoggedOncePerPublishedValue(CapturedOutput output)
      throws InterruptedException {
    // A mismatch can last indefinitely (a trailing slash after an upgrade): every cache refresh
    // keeps the DOWN detail, but the log names the published issuer once.
    try (StubIdentityProvider provider =
        StubIdentityProvider.start("owl-mast", "https://other.example/realms/owl-mast")) {
      Duration ttl = Duration.ofMillis(100);
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(), new IdentityProperties(provider.issuerUri(), true), ttl);
      for (int i = 0; i < 4; i++) {
        Health health = indicator.health().block(Duration.ofSeconds(10));
        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
        assertThat(health.getDetails())
            .containsEntry("publishedIssuer", "https://other.example/realms/owl-mast");
        Thread.sleep(ttl.toMillis() * 3);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(4);
      assertThat(output.getAll().lines().filter(line -> line.contains(MISMATCH_WARNING)))
          .hasSize(1)
          .allMatch(line -> line.contains("[https://other.example/realms/owl-mast] differs"))
          .allMatch(line -> line.contains("WARN"));
    }
  }

  @Test
  void aMatchingIssuerLogsNoMismatchWarning(CapturedOutput output) {
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      assertThat(check(provider.issuerUri()).getStatus()).isEqualTo(Status.UP);
      assertThat(output.getAll()).doesNotContain(MISMATCH_WARNING);
    }
  }

  @Test
  void theCacheIntervalIsCountedFromTheStartOfTheDiscoveryRequest() throws InterruptedException {
    // A provider that takes 1.5 s to answer, and a 2 s interval. Counted from the answer, the
    // result would be served until 3.5 s after the first request; counted from the request it
    // expires at 2 s, so an evaluation 2.4 s after the first one starts a new request. That is
    // what makes "a probe period greater than CACHE_TTL" sufficient for a fresh result per probe.
    try (StubIdentityProvider provider =
        StubIdentityProvider.startSlow("owl-mast", Duration.ofMillis(1500))) {
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(),
              new IdentityProperties(provider.issuerUri(), true),
              Duration.ofSeconds(2));
      long started = System.nanoTime();
      assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus()).isEqualTo(Status.UP);
      // Still inside the interval: the answer is shared, no second request.
      assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus()).isEqualTo(Status.UP);
      assertThat(provider.discoveryRequests()).isEqualTo(1);
      long elapsedMillis = Duration.ofNanos(System.nanoTime() - started).toMillis();
      Thread.sleep(Math.max(0, 2400 - elapsedMillis));
      assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus()).isEqualTo(Status.UP);
      assertThat(provider.discoveryRequests()).isEqualTo(2);
    }
  }

  @Test
  void anAnswerSlowerThanTheIntervalIsDeliveredButNotKept() {
    try (StubIdentityProvider provider =
        StubIdentityProvider.startSlow("owl-mast", Duration.ofMillis(400))) {
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(),
              new IdentityProperties(provider.issuerUri(), true),
              Duration.ofMillis(100));
      for (int i = 1; i <= 3; i++) {
        assertThat(indicator.health().block(Duration.ofSeconds(10)).getStatus())
            .isEqualTo(Status.UP);
        assertThat(provider.discoveryRequests()).isEqualTo(i);
      }
    }
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
