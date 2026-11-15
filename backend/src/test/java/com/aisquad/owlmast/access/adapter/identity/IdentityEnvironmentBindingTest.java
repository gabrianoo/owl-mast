package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.SystemEnvironmentPropertySource;

/**
 * The environment variables the installation chart sets reach the properties the backend reads,
 * through the application's own {@code application.yaml}. The chart tests prove the names are
 * rendered; this proves a rendered name is bound and not silently ignored.
 */
class IdentityEnvironmentBindingTest {

  @Configuration(proxyBeanMethods = false)
  @EnableConfigurationProperties({IdentityProperties.class, SignInProperties.class})
  static class Bound {}

  @Test
  void theBundledInstallationsVariablesAreBound() {
    Map<String, Object> environment = new HashMap<>(external());
    environment.put("OWLMAST_IDENTITY_BACKCHANNEL_URI", "http://owl-mast-keycloak:8080/realms/x");
    environment.put("OWLMAST_IDENTITY_ALLOW_INSECURE_BACKCHANNEL", "true");

    runner(environment)
        .run(context -> {
          assertThat(context).hasNotFailed();
          IdentityProperties identity = context.getBean(IdentityProperties.class);
          assertThat(identity.issuerUri()).isEqualTo("https://id.example/realms/x");
          assertThat(identity.allowInsecureIssuer()).isFalse();
          assertThat(identity.backchannelUri()).isEqualTo("http://owl-mast-keycloak:8080/realms/x");
          assertThat(identity.allowInsecureBackchannel()).isTrue();
          assertThat(identity.discoveryUri())
              .hasToString(
                  "http://owl-mast-keycloak:8080/realms/x/.well-known/openid-configuration");
          SignInProperties signIn = context.getBean(SignInProperties.class);
          assertThat(signIn.clientId()).isEqualTo("owl-mast-web");
          // As a Secret file delivers it, with its line end.
          assertThat(signIn.clientSecret()).isEqualTo("synthetic-secret");
          assertThat(signIn.applicationOrigin()).isEqualTo("https://owl.example");
          assertThat(signIn.audience()).isEqualTo("owl-mast-web");
          assertThat(signIn.tenant()).isEqualTo("default");
        });
  }

  @Test
  void withoutTheBackchannelVariableTheIssuerIsReadOnItsOwnAddress() {
    runner(external())
        .run(context -> {
          assertThat(context).hasNotFailed();
          IdentityProperties identity = context.getBean(IdentityProperties.class);
          assertThat(identity.backchannelUri()).isNull();
          assertThat(identity.discoveryUri())
              .hasToString("https://id.example/realms/x/.well-known/openid-configuration");
        });
  }

  /** The plaintext back channel is refused unless its own variable allows it. */
  @Test
  void aPlaintextBackchannelNeedsItsOwnVariable() {
    Map<String, Object> environment = new HashMap<>(external());
    environment.put("OWLMAST_IDENTITY_BACKCHANNEL_URI", "http://owl-mast-keycloak:8080/realms/x");

    runner(environment)
        .run(context -> {
          assertThat(context).hasFailed();
          assertThat(context.getStartupFailure())
              .rootCause()
              .hasMessageContaining("owlmast.identity.backchannel-uri must use https");
        });
  }

  private static Map<String, Object> external() {
    return Map.of(
        "OWLMAST_IDENTITY_ISSUER_URI", "https://id.example/realms/x",
        "OWLMAST_IDENTITY_CLIENT_ID", "owl-mast-web",
        "OWLMAST_IDENTITY_CLIENT_SECRET", "synthetic-secret\n",
        "OWLMAST_IDENTITY_APPLICATION_ORIGIN", "https://owl.example");
  }

  private static ApplicationContextRunner runner(Map<String, Object> environment) {
    return new ApplicationContextRunner()
        .withInitializer(context ->
            context
                .getEnvironment()
                .getPropertySources()
                .addFirst(new SystemEnvironmentPropertySource("test-environment", environment)))
        .withInitializer(new ConfigDataApplicationContextInitializer())
        .withUserConfiguration(Bound.class);
  }
}
