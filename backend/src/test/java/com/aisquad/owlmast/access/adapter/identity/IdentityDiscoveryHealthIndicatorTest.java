package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.testing.StubIdentityProvider;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.Status;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.test.scheduler.VirtualTimeScheduler;

@ExtendWith(OutputCaptureExtension.class)
class IdentityDiscoveryHealthIndicatorTest {

  private static final String MISMATCH_WARNING = "Identity discovery: the published issuer [";

  /** Real-time bound for one answer of the local stub; never part of a timing assertion. */
  private static final Duration ANSWER = Duration.ofSeconds(30);

  /**
   * An indicator whose cache interval is measured and expired on {@code time} alone: the test moves
   * the clock, so the age of a result does not depend on the speed of the machine.
   */
  private static IdentityDiscoveryHealthIndicator onVirtualTime(
      StubIdentityProvider provider, Duration ttl, VirtualTimeScheduler time) {
    return new IdentityDiscoveryHealthIndicator(
        WebClient.create(),
        new IdentityProperties(provider.issuerUri(), true),
        ttl,
        () -> time.now(TimeUnit.NANOSECONDS),
        time);
  }

  /** Waits (real time, bounded) until the provider has received {@code count} requests. */
  private static void awaitRequests(StubIdentityProvider provider, int count)
      throws InterruptedException {
    long deadline = System.nanoTime() + ANSWER.toNanos();
    while (provider.discoveryRequests() < count && System.nanoTime() < deadline) {
      Thread.sleep(5);
    }
    assertThat(provider.discoveryRequests()).isEqualTo(count);
  }

  private static List<String> mismatchWarnings(CapturedOutput output) {
    return output.getAll().lines().filter(line -> line.contains(MISMATCH_WARNING)).toList();
  }

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
  void aDownResultIsCachedTooAndRefreshedAfterTheInterval() {
    VirtualTimeScheduler time = VirtualTimeScheduler.create();
    try (StubIdentityProvider provider =
        StubIdentityProvider.start("owl-mast", "https://other.example/realms/owl-mast")) {
      Duration ttl = Duration.ofMillis(300);
      IdentityDiscoveryHealthIndicator indicator = onVirtualTime(provider, ttl, time);
      for (int i = 0; i < 10; i++) {
        assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.DOWN);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(1);
      time.advanceTimeBy(ttl.minusMillis(1));
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.DOWN);
      assertThat(provider.discoveryRequests()).isEqualTo(1);
      time.advanceTimeBy(Duration.ofMillis(1));
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.DOWN);
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
  void aPositiveIntervalExpiresOnTheProductionClockAndTimer() throws Exception {
    // The only test that lets a positive interval run out in real time, on the pair production
    // uses (System::nanoTime and Schedulers.parallel(), through the three-argument constructor).
    // It checks the expiry side only, which cannot fail on a slow machine: there is no "still
    // cached just before the interval ends" assertion here; the virtual-clock tests hold those.
    Duration ttl = Duration.ofMillis(250);
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      for (int attempt = 1; attempt <= 5; attempt++) {
        IdentityDiscoveryHealthIndicator indicator =
            new IdentityDiscoveryHealthIndicator(
                WebClient.create(), new IdentityProperties(provider.issuerUri(), true), ttl);
        int before = provider.discoveryRequests();
        long asked = System.nanoTime();
        assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.UP);
        long answeredAfter = System.nanoTime() - asked;
        assertThat(provider.discoveryRequests()).isEqualTo(before + 1);
        if (answeredAfter >= ttl.toNanos()) {
          // The answer may have used up the interval: then nothing was handed to the timer and
          // this attempt would prove nothing. A cold first request can be that slow; retry.
          continue;
        }
        // The answer came back inside the interval, so the rest of it was handed to the timer.
        // Only that timer can clear the result: keep evaluating until a second request is made.
        long deadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();
        while (provider.discoveryRequests() < before + 2 && System.nanoTime() < deadline) {
          Thread.sleep(25);
          assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.UP);
        }
        assertThat(provider.discoveryRequests())
            .as("a second discovery request once the %s interval has run out", ttl)
            .isEqualTo(before + 2);
        return;
      }
      throw new AssertionError("five discovery answers in a row took longer than " + ttl);
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
  void theMismatchWarningIsLoggedOncePerPublishedValue(CapturedOutput output) {
    // A mismatch can last indefinitely (a trailing slash after an upgrade): every cache refresh
    // keeps the DOWN detail, but the log names the published issuer once.
    VirtualTimeScheduler time = VirtualTimeScheduler.create();
    try (StubIdentityProvider provider =
        StubIdentityProvider.start("owl-mast", "https://other.example/realms/owl-mast")) {
      Duration ttl = Duration.ofMillis(100);
      IdentityDiscoveryHealthIndicator indicator = onVirtualTime(provider, ttl, time);
      for (int i = 0; i < 4; i++) {
        Health health = indicator.health().block(ANSWER);
        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
        assertThat(health.getDetails())
            .containsEntry("publishedIssuer", "https://other.example/realms/owl-mast");
        time.advanceTimeBy(ttl);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(4);
      assertThat(mismatchWarnings(output))
          .hasSize(1)
          .allMatch(line -> line.contains("[https://other.example/realms/owl-mast] differs"))
          .allMatch(line -> line.contains("WARN"));
    }
  }

  @Test
  void theMismatchWarningIsLoggedAgainWhenThePublishedValueChanges(CapturedOutput output) {
    // A zero interval: every evaluation asks the provider, so each one sees the current value.
    String first = "https://first.example/realms/owl-mast";
    String second = "https://second.example/realms/owl-mast";
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast", first)) {
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(),
              new IdentityProperties(provider.issuerUri(), true),
              Duration.ZERO);
      for (String published : List.of(first, first, second, second, first)) {
        provider.publish(published);
        Health health = indicator.health().block(ANSWER);
        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
        assertThat(health.getDetails()).containsEntry("publishedIssuer", published);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(5);
      // One line per CHANGE of the published value, in order: a repeated value adds none, a new
      // value is reported, and so is the first value when it comes back.
      List<String> warnings = mismatchWarnings(output);
      assertThat(warnings).hasSize(3);
      assertThat(warnings.get(0)).contains("[" + first + "] differs");
      assertThat(warnings.get(1)).contains("[" + second + "] differs");
      assertThat(warnings.get(2)).contains("[" + first + "] differs");
    }
  }

  @Test
  void theMismatchWarningIsLoggedAgainAfterTheIssuerMatchedInBetween(CapturedOutput output) {
    String wrong = "https://other.example/realms/owl-mast";
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast", wrong)) {
      IdentityDiscoveryHealthIndicator indicator =
          new IdentityDiscoveryHealthIndicator(
              WebClient.create(),
              new IdentityProperties(provider.issuerUri(), true),
              Duration.ZERO);
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.DOWN);
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.DOWN);
      assertThat(mismatchWarnings(output)).hasSize(1);

      // The provider is corrected: the issuer matches, readiness is UP, nothing is logged.
      provider.publish(null);
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.UP);
      assertThat(mismatchWarnings(output)).hasSize(1);

      // The SAME wrong value comes back: a new incident, so it is reported again, once.
      provider.publish(wrong);
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.DOWN);
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.DOWN);
      assertThat(provider.discoveryRequests()).isEqualTo(5);
      assertThat(mismatchWarnings(output))
          .hasSize(2)
          .allMatch(line -> line.contains("[" + wrong + "] differs"))
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
  void theCacheIntervalIsCountedFromTheStartOfTheDiscoveryRequest() throws Exception {
    // A provider that takes 1.5 s to answer, and a 2 s interval. Counted from the answer, the
    // result would be served until 3.5 s after the request; counted from the request it expires at
    // 2 s. That is what makes "a probe period greater than CACHE_TTL" sufficient for a fresh
    // result per probe. Time is virtual: the provider holds its answer until the test has moved
    // the clock, so no margin depends on how fast this machine connects or answers.
    VirtualTimeScheduler time = VirtualTimeScheduler.create();
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      IdentityDiscoveryHealthIndicator indicator =
          onVirtualTime(provider, Duration.ofSeconds(2), time);
      provider.holdAnswers();
      CompletableFuture<Health> first = indicator.health().toFuture();
      awaitRequests(provider, 1);
      time.advanceTimeBy(Duration.ofMillis(1500));
      assertThat(first).isNotDone();
      provider.releaseAnswers();
      assertThat(first.get(ANSWER.toSeconds(), TimeUnit.SECONDS).getStatus()).isEqualTo(Status.UP);

      // 1.5 s after the request: inside the interval, the answer is shared.
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.UP);
      assertThat(provider.discoveryRequests()).isEqualTo(1);
      // 1 ms before the interval ends, still counted from the request.
      time.advanceTimeBy(Duration.ofMillis(499));
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.UP);
      assertThat(provider.discoveryRequests()).isEqualTo(1);
      // 2 s after the request (0.5 s after the answer): expired, a new request.
      time.advanceTimeBy(Duration.ofMillis(1));
      assertThat(indicator.health().block(ANSWER).getStatus()).isEqualTo(Status.UP);
      assertThat(provider.discoveryRequests()).isEqualTo(2);
    }
  }

  @Test
  void anAnswerThatTookTheWholeIntervalIsDeliveredButNotKept() throws Exception {
    VirtualTimeScheduler time = VirtualTimeScheduler.create();
    try (StubIdentityProvider provider = StubIdentityProvider.start("owl-mast")) {
      IdentityDiscoveryHealthIndicator indicator =
          onVirtualTime(provider, Duration.ofSeconds(2), time);
      for (int i = 1; i <= 3; i++) {
        provider.holdAnswers();
        CompletableFuture<Health> evaluation = indicator.health().toFuture();
        awaitRequests(provider, i);
        // exactly the interval on the first round, more than it afterwards
        time.advanceTimeBy(Duration.ofSeconds(2).plusMillis(i - 1));
        provider.releaseAnswers();
        assertThat(evaluation.get(ANSWER.toSeconds(), TimeUnit.SECONDS).getStatus())
            .isEqualTo(Status.UP);
      }
      assertThat(provider.discoveryRequests()).isEqualTo(3);
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
