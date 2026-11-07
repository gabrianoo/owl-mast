package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

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
    assertThatThrownBy(() -> new IdentityProperties("realms/owl-mast"))
        .hasMessageContaining("absolute URL");
    assertThatThrownBy(() -> new IdentityProperties("ftp://idp.example/realms/x"))
        .hasMessageContaining("http or https");
  }

  @Test
  void validIssuerIsNormalisedAndExposesDiscoveryLocation() {
    runner
        .withPropertyValues("owlmast.identity.issuer-uri=https://idp.example/realms/owl-mast/")
        .run(context -> {
          assertThat(context).hasNotFailed();
          IdentityProperties properties = context.getBean(IdentityProperties.class);
          assertThat(properties.issuerUri()).isEqualTo("https://idp.example/realms/owl-mast");
          assertThat(properties.discoveryUri())
              .hasToString("https://idp.example/realms/owl-mast/.well-known/openid-configuration");
          assertThat(context).hasBean("identityDiscovery");
        });
  }
}
