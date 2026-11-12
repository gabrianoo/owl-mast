package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class IdentityPropertiesTest {

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner().withUserConfiguration(IdentityConfiguration.class);

  @Test
  void missingIssuerFailsStartupNamingTheProperty() {
    runner.run(context -> {
      assertThat(context).hasFailed();
      assertThat(context.getStartupFailure())
          .rootCause()
          .hasMessageContaining("owlmast.identity.issuer-uri is required")
          .hasMessageContaining("never disables authentication");
    });
  }

  @Test
  void blankIssuerFailsStartup() {
    runner
        .withPropertyValues("owlmast.identity.issuer-uri=  ")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void relativeOrNonHttpIssuerIsRejected() {
    assertThatThrownBy(() -> new IdentityProperties("realms/owl-mast", false))
        .hasMessageContaining("absolute URL");
    assertThatThrownBy(() -> new IdentityProperties("ftp://idp.example/realms/x", false))
        .hasMessageContaining("http or https");
  }

  /** What IdentityProperties says for each refusal reason named in the sample file. */
  private static final Map<String, String> REASONS =
      Map.of(
          "host", "owlmast.identity.issuer-uri must be an absolute URL with a host",
          "port", "owlmast.identity.issuer-uri must use a port between 1 and 65535",
          "userinfo", "owlmast.identity.issuer-uri must not contain user info",
          "query", "owlmast.identity.issuer-uri must not contain a query or fragment",
          "insecure", "owlmast.identity.issuer-uri must use https");

  /** One line of the sample file: kind, refusal reason (empty when accepted) and issuer. */
  record Sample(String kind, String reason, String issuer) {

    static Sample parse(String line) {
      int space = line.indexOf(' ');
      if (space <= 0 || space == line.length() - 1 || line.charAt(space + 1) == ' ') {
        throw new AssertionError("malformed sample line: " + line);
      }
      String head = line.substring(0, space);
      int colon = head.indexOf(':');
      String kind = colon < 0 ? head : head.substring(0, colon);
      String reason = colon < 0 ? "" : head.substring(colon + 1);
      boolean refusal = kind.equals("refuse") || kind.equals("refuse-insecure");
      boolean known =
          List.of("accept", "refuse", "chart-refuse", "accept-insecure", "refuse-insecure")
              .contains(kind);
      // "insecure" is what an accept-insecure line is refused for without the opt-in, never a
      // reason a line may name.
      boolean named = REASONS.containsKey(reason) && !reason.equals("insecure");
      if (!known || refusal != named || (!refusal && colon >= 0)) {
        throw new AssertionError("malformed sample line: " + line);
      }
      return new Sample(kind, reason, line.substring(space + 1));
    }
  }

  private static void assertRefused(Sample sample, boolean allowInsecure, String reason) {
    assertThatThrownBy(() -> new IdentityProperties(sample.issuer(), allowInsecure))
        .as(sample.toString())
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining(REASONS.get(reason));
  }

  /**
   * The chart's issuer rule and this class are compared on one sample file: the chart render test
   * (deploy/tests/test_chart_render.py) renders every {@code accept} line and is refused on every
   * {@code refuse} and {@code chart-refuse} line. Here every {@code accept} and {@code
   * chart-refuse} line must construct and every {@code refuse} line must throw for the reason the
   * line names, so the chart never renders an issuer that stops the backend at startup, and a
   * sample cannot pass by being refused for something else. The {@code -insecure} kinds run the
   * same comparison for plaintext issuers, with and without the opt-in.
   */
  @Test
  void theChartsIssuerSamplesAgreeWithThisClass() throws IOException {
    List<String> lines;
    try (InputStream in = getClass().getResourceAsStream("/identity/issuer-samples.txt")) {
      assertThat(in).as("identity/issuer-samples.txt on the test classpath").isNotNull();
      lines = new String(in.readAllBytes(), StandardCharsets.UTF_8).lines().toList();
    }
    Map<String, Integer> seen = new HashMap<>();
    for (String line : lines) {
      if (line.isBlank() || line.startsWith("#")) {
        continue;
      }
      Sample sample = Sample.parse(line);
      String issuer = sample.issuer();
      switch (sample.kind()) {
        case "accept", "chart-refuse" ->
            assertThat(new IdentityProperties(issuer, false).issuerUri())
                .as(line)
                .isEqualTo(issuer);
        case "refuse" -> assertRefused(sample, false, sample.reason());
        case "accept-insecure" -> {
          assertThat(new IdentityProperties(issuer, true).issuerUri()).as(line).isEqualTo(issuer);
          assertRefused(sample, false, "insecure");
        }
        case "refuse-insecure" -> assertRefused(sample, true, sample.reason());
        default -> throw new AssertionError("unknown sample kind: " + line);
      }
      seen.merge(sample.kind(), 1, Integer::sum);
    }
    assertThat(seen.get("accept") + seen.get("chart-refuse")).isGreaterThanOrEqualTo(10);
    assertThat(seen.get("refuse")).isGreaterThanOrEqualTo(15);
    assertThat(seen.get("accept-insecure")).isGreaterThanOrEqualTo(3);
    assertThat(seen.get("refuse-insecure")).isGreaterThanOrEqualTo(4);
  }

  @Test
  void aMalformedSampleLineIsNamed() {
    for (String line :
        new String[] {
          "accept",
          "accepthttps://idp.example",
          "refuse https://idp.123/x",
          "refuse:nonsense x",
          "accept:host https://idp.example",
          "accept  https://idp.example",
          "accept ",
          "sometimes https://idp.example",
          "refuse:insecure http://idp.example"
        }) {
      assertThatThrownBy(() -> Sample.parse(line))
          .as(line)
          .isInstanceOf(AssertionError.class)
          .hasMessage("malformed sample line: " + line);
    }
    assertThat(Sample.parse("refuse:port https://idp.example:0/x"))
        .isEqualTo(new Sample("refuse", "port", "https://idp.example:0/x"));
  }

  @Test
  void issuerWithQueryOrFragmentIsRejectedNamingTheProperty() {
    for (String issuer :
        new String[] {
          "https://idp.example/realms/x?a=b",
          "https://idp.example/realms/x?",
          "https://idp.example/realms/x#frag",
          "https://idp.example/realms/x/?a=b#frag"
        }) {
      assertThatThrownBy(() -> new IdentityProperties(issuer, false))
          .as(issuer)
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("owlmast.identity.issuer-uri must not contain a query or fragment");
    }
  }

  @Test
  void issuerWithUserInfoIsRejectedNamingTheProperty() {
    for (String issuer :
        new String[] {
          "https://user@idp.example/realms/x", "https://user:pw@idp.example/realms/x"
        }) {
      assertThatThrownBy(() -> new IdentityProperties(issuer, false))
          .as(issuer)
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("owlmast.identity.issuer-uri must not contain user info");
    }
  }

  @Test
  void plaintextIssuerNeedsTheExplicitOptIn() {
    for (String issuer :
        new String[] {
          "http://owl-mast-keycloak:8080/realms/owl-mast",
          "http://idp.example/realms/x",
          "HTTP://idp.example/realms/x",
          "http://localhost:8080/realms/x"
        }) {
      assertThatThrownBy(() -> new IdentityProperties(issuer, false))
          .as(issuer)
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("owlmast.identity.issuer-uri must use https")
          .hasMessageContaining("owlmast.identity.allow-insecure-issuer=true");
      assertThat(new IdentityProperties(issuer, true).issuerUri()).isEqualTo(issuer);
    }
    // The opt-in never weakens anything else: https stays accepted, other schemes stay refused.
    assertThat(new IdentityProperties("https://idp.example/realms/x", true).issuerUri())
        .isEqualTo("https://idp.example/realms/x");
    assertThatThrownBy(() -> new IdentityProperties("ftp://idp.example/realms/x", true))
        .hasMessageContaining("http or https");
  }

  @Test
  void plaintextIssuerFailsStartupUnlessThePropertyAllowsIt() {
    runner
        .withPropertyValues("owlmast.identity.issuer-uri=http://owl-mast-keycloak:8080/realms/x")
        .run(context -> {
          assertThat(context).hasFailed();
          assertThat(context.getStartupFailure())
              .rootCause()
              .hasMessageContaining("owlmast.identity.issuer-uri must use https");
        });
    runner
        .withPropertyValues(
            "owlmast.identity.issuer-uri=http://owl-mast-keycloak:8080/realms/x",
            "owlmast.identity.allow-insecure-issuer=true")
        .run(context -> {
          assertThat(context).hasNotFailed();
          assertThat(context.getBean(IdentityProperties.class).allowInsecureIssuer()).isTrue();
        });
  }

  @Test
  void issuerPortMustBeOneAConnectionCanUse() {
    for (String issuer :
        new String[] {
          "https://idp.example:0/realms/x",
          "https://idp.example:65536/realms/x",
          "https://idp.example:99999/realms/x"
        }) {
      assertThatThrownBy(() -> new IdentityProperties(issuer, false))
          .as(issuer)
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("owlmast.identity.issuer-uri must use a port between 1 and 65535");
    }
    for (String issuer :
        new String[] {
          "https://idp.example/realms/x",
          "https://idp.example:1/realms/x",
          "https://idp.example:65535/realms/x"
        }) {
      assertThat(new IdentityProperties(issuer, false).issuerUri()).isEqualTo(issuer);
    }
  }

  @Test
  void issuerWithQueryFailsStartup() {
    runner
        .withPropertyValues("owlmast.identity.issuer-uri=https://idp.example/realms/x?a=b")
        .run(context -> {
          assertThat(context).hasFailed();
          assertThat(context.getStartupFailure())
              .rootCause()
              .hasMessageContaining(
                  "owlmast.identity.issuer-uri must not contain a query or fragment");
        });
  }

  @Test
  void validIssuerIsKeptVerbatimAndExposesDiscoveryLocation() {
    runner
        .withPropertyValues("owlmast.identity.issuer-uri= https://idp.example/realms/owl-mast/ ")
        .run(context -> {
          assertThat(context).hasNotFailed();
          IdentityProperties properties = context.getBean(IdentityProperties.class);
          // Only surrounding whitespace is removed: the trailing slash is part of the issuer.
          assertThat(properties.issuerUri()).isEqualTo("https://idp.example/realms/owl-mast/");
          assertThat(properties.allowInsecureIssuer()).isFalse();
          assertThat(properties.discoveryUri())
              .hasToString("https://idp.example/realms/owl-mast/.well-known/openid-configuration");
          assertThat(context).hasBean("identityDiscovery");
        });
    assertThat(new IdentityProperties("https://idp.example/realms/owl-mast", false).discoveryUri())
        .hasToString("https://idp.example/realms/owl-mast/.well-known/openid-configuration");
    assertThat(new IdentityProperties("https://idp.example/", false).discoveryUri())
        .hasToString("https://idp.example/.well-known/openid-configuration");
  }
}
