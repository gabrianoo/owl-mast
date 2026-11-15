package com.aisquad.owlmast.testing;

import java.time.Duration;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistrar;

/**
 * Points the backend at a {@link SyntheticKeycloak} owned by the context: issuer, client and
 * secret. The application origin is taken from {@code owlmast.sign-in.application-origin} when the
 * run sets it (the browser smoke run names the frontend's address) and is {@value
 * #DEFAULT_APPLICATION_ORIGIN} otherwise.
 *
 * <p>The access token lifetime is {@code owlmast.fixture.access-token-lifespan} (default five
 * minutes, Keycloak's own default). The integration tests set it to thirty seconds, which is inside
 * the minute before expiry in which the backend renews, so every request asks Keycloak whether the
 * session still stands and an ended session is noticed at the next request.
 */
@TestConfiguration(proxyBeanMethods = false)
public class SyntheticKeycloakConfiguration {

  public static final String DEFAULT_APPLICATION_ORIGIN = "http://localhost:8080";
  public static final String APPLICATION_ORIGIN_PROPERTY = "owlmast.sign-in.application-origin";
  public static final String LIFESPAN_PROPERTY = "owlmast.fixture.access-token-lifespan";

  @Bean(destroyMethod = "close")
  SyntheticKeycloak syntheticKeycloak(Environment environment) {
    return SyntheticKeycloak.start(
        applicationOrigin(environment),
        environment.getProperty(LIFESPAN_PROPERTY, Duration.class, Duration.ofMinutes(5)));
  }

  @Bean
  DynamicPropertyRegistrar syntheticKeycloakProperties(
      SyntheticKeycloak keycloak, Environment environment) {
    return registry -> {
      registry.add("owlmast.identity.issuer-uri", keycloak::issuerUri);
      // The container speaks plaintext on loopback; the backend refuses that without the opt-in.
      registry.add("owlmast.identity.allow-insecure-issuer", () -> "true");
      registry.add("owlmast.sign-in.client-id", () -> SyntheticKeycloak.CLIENT_ID);
      registry.add("owlmast.sign-in.client-secret", keycloak::clientSecret);
      // Registered values outrank the application's own configuration, so the run's choice is
      // passed on rather than replaced.
      String applicationOrigin = applicationOrigin(environment);
      registry.add(APPLICATION_ORIGIN_PROPERTY, () -> applicationOrigin);
    };
  }

  /** The origin the run named, or the default: the application's own file leaves it empty. */
  private static String applicationOrigin(Environment environment) {
    String chosen = environment.getProperty(APPLICATION_ORIGIN_PROPERTY);
    return chosen == null || chosen.isBlank() ? DEFAULT_APPLICATION_ORIGIN : chosen;
  }
}
