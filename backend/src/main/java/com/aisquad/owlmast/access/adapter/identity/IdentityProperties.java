package com.aisquad.owlmast.access.adapter.identity;

import java.net.URI;
import java.util.Locale;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * The OpenID Connect issuer this installation trusts. Required: there is no configuration that runs
 * Owl Mast without an identity provider, bundled or external (AC2).
 */
@ConfigurationProperties("owlmast.identity")
public record IdentityProperties(String issuerUri) {

  private static final String PROPERTY = "owlmast.identity.issuer-uri";

  public IdentityProperties {
    if (issuerUri == null || issuerUri.isBlank()) {
      throw new IllegalArgumentException(
          PROPERTY
              + " is required: set it to the bundled Keycloak realm or a compatible external"
              + " issuer; disabling the identity bundle never disables authentication");
    }
    URI parsed = URI.create(issuerUri.strip());
    if (!parsed.isAbsolute() || parsed.getHost() == null) {
      throw new IllegalArgumentException(PROPERTY + " must be an absolute URL with a host");
    }
    String scheme = parsed.getScheme().toLowerCase(Locale.ROOT);
    if (!scheme.equals("http") && !scheme.equals("https")) {
      throw new IllegalArgumentException(PROPERTY + " must use http or https");
    }
    if (parsed.getRawUserInfo() != null) {
      throw new IllegalArgumentException(PROPERTY + " must not contain user info");
    }
    if (parsed.getRawQuery() != null || parsed.getRawFragment() != null) {
      throw new IllegalArgumentException(
          PROPERTY
              + " must not contain a query or fragment: the discovery document is resolved below"
              + " the issuer path");
    }
    issuerUri = stripTrailingSlash(issuerUri.strip());
  }

  /** Discovery document location per OpenID Connect Discovery 1.0 section 4. */
  public URI discoveryUri() {
    return URI.create(issuerUri + "/.well-known/openid-configuration");
  }

  static String stripTrailingSlash(String value) {
    return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
  }
}
