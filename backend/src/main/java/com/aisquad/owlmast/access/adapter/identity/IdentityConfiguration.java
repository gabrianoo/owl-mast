package com.aisquad.owlmast.access.adapter.identity;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

/** Wires the identity-provider contract; the indicator joins the readiness group by name. */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(IdentityProperties.class)
class IdentityConfiguration {

  @Bean("identityDiscovery")
  IdentityDiscoveryHealthIndicator identityDiscovery(IdentityProperties properties) {
    // A plain client: discovery is a small unauthenticated GET, no codecs or observation needed.
    return new IdentityDiscoveryHealthIndicator(WebClient.create(), properties);
  }
}
