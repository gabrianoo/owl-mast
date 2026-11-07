package com.aisquad.owlmast.testing;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistrar;

/** Points {@code owlmast.identity.issuer-uri} at a stub discovery endpoint owned by the context. */
@TestConfiguration(proxyBeanMethods = false)
public class StubIdentityConfiguration {

  @Bean(destroyMethod = "close")
  StubIdentityProvider stubIdentityProvider() {
    return StubIdentityProvider.start("owl-mast");
  }

  @Bean
  DynamicPropertyRegistrar identityIssuerProperty(StubIdentityProvider provider) {
    return registry -> registry.add("owlmast.identity.issuer-uri", provider::issuerUri);
  }
}
