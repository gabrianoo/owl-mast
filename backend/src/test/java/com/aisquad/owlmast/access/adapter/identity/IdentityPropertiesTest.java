package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
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

  /**
   * The chart's issuer rule and this class are compared on one sample file: the chart render test
   * (deploy/tests/test_chart_render.py) renders every {@code accept} line and is refused on every
   * {@code refuse} and {@code chart-refuse} line. Here every {@code accept} and {@code
   * chart-refuse} line must construct and every {@code refuse} line must throw, so the chart never
   * renders an issuer that stops the backend at startup.
   */
  @Test
  void theChartsIssuerSamplesAgreeWithThisClass() throws IOException {
    List<String> lines;
    try (InputStream in = getClass().getResourceAsStream("/identity/issuer-samples.txt")) {
      assertThat(in).as("identity/issuer-samples.txt on the test classpath").isNotNull();
      lines = new String(in.readAllBytes(), StandardCharsets.UTF_8).lines().toList();
    }
    int accepted = 0;
    int refused = 0;
    for (String line : lines) {
      if (line.isBlank() || line.startsWith("#")) {
        continue;
      }
      String kind = line.substring(0, line.indexOf(' '));
      String issuer = line.substring(line.indexOf(' ') + 1);
      switch (kind) {
        case "accept", "chart-refuse" -> {
          assertThat(new IdentityProperties(issuer, false).issuerUri()).as(line).isEqualTo(issuer);
          accepted++;
        }
        case "refuse" -> {
          assertThatThrownBy(() -> new IdentityProperties(issuer, false))
              .as(line)
              .isInstanceOf(IllegalArgumentException.class);
          refused++;
        }
        default -> throw new AssertionError("unknown sample kind: " + line);
      }
    }
    assertThat(accepted).isGreaterThanOrEqualTo(10);
    assertThat(refused).isGreaterThanOrEqualTo(15);
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
