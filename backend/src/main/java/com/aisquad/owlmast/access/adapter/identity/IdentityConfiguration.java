package com.aisquad.owlmast.access.adapter.identity;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

/** Wires the identity-provider contract; the indicator joins the readiness group by name. */
@Slf4j
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(IdentityProperties.class)
class IdentityConfiguration {

  @Bean("identityDiscovery")
  IdentityDiscoveryHealthIndicator identityDiscovery(IdentityProperties properties) {
    // One line at start-up naming what was bound: the issuer is configuration, not a secret, and
    // the
    // image check (scripts/verify-backend-image.sh) reads this line as its proof that the identity
    // properties were bound and validated.
    log.info(
        "Identity issuer {} (plaintext issuer accepted: {})",
        properties.issuerUri(),
        properties.allowInsecureIssuer());
    // A plain client: discovery is a small unauthenticated GET, no codecs or observation needed.
    return new IdentityDiscoveryHealthIndicator(WebClient.create(), properties);
  }
}
