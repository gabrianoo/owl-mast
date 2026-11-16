package com.aisquad.owlmast.testing;

import java.util.UUID;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistrar;
import org.springframework.test.context.DynamicPropertyRegistry;

/** Points {@code owlmast.identity.issuer-uri} at a stub discovery endpoint owned by the context. */
@TestConfiguration(proxyBeanMethods = false)
public class StubIdentityConfiguration {

  @Bean(destroyMethod = "close")
  StubIdentityProvider stubIdentityProvider() {
    return StubIdentityProvider.start("owl-mast");
  }

  @Bean
  DynamicPropertyRegistrar identityIssuerProperty(StubIdentityProvider provider) {
    return registry -> {
      registry.add("owlmast.identity.issuer-uri", provider::issuerUri);
      // The stub speaks plaintext on loopback; the backend refuses http issuers without this
      // opt-in.
      registry.add("owlmast.identity.allow-insecure-issuer", () -> "true");
      registerSignIn(registry);
    };
  }

  /**
   * Sign-in is always configured (OM-02.01): a synthetic client with a secret made up for the run.
   * A stub issuer publishes no token or key endpoint, so a context using it starts and can become
   * ready, and every sign-in step answers "unavailable".
   */
  public static void registerSignIn(DynamicPropertyRegistry registry) {
    String secret = UUID.randomUUID().toString();
    registry.add("owlmast.sign-in.client-id", () -> "owl-mast-web");
    registry.add("owlmast.sign-in.client-secret", () -> secret);
    registry.add("owlmast.sign-in.application-origin", () -> "http://localhost:8080");
  }
}
