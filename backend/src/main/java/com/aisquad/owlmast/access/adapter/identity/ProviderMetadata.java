package com.aisquad.owlmast.access.adapter.identity;

import java.util.Objects;
import java.util.Optional;

/**
 * What the backend uses from the issuer's discovery document. {@code issuer} equals the configured
 * issuer exactly, or the document is refused. The authorization endpoint is where the browser goes;
 * the token and key endpoints are where the backend goes, which for the bundled Keycloak is the
 * cluster-local address the document was fetched from.
 */
public record ProviderMetadata(
    String issuer, String authorizationEndpoint, String tokenEndpoint, String jwksUri) {

  private static final String TOKEN_SUFFIX = "/token";

  public ProviderMetadata {
    Objects.requireNonNull(issuer, "issuer");
    Objects.requireNonNull(authorizationEndpoint, "authorizationEndpoint");
    Objects.requireNonNull(tokenEndpoint, "tokenEndpoint");
    Objects.requireNonNull(jwksUri, "jwksUri");
  }

  /**
   * Keycloak's logout endpoint on the address the backend uses, or empty when the token endpoint
   * does not have Keycloak's layout. Keycloak serves it next to the token endpoint ({@code
   * .../protocol/openid-connect/logout}) and ends the whole provider session when a confidential
   * client posts its refresh token there. The discovery document's {@code end_session_endpoint} is
   * not used: it is the browser's address, which the backend may be unable to reach, and the
   * browser flow would need a token in the browser.
   */
  public Optional<String> logoutEndpoint() {
    return tokenEndpoint.endsWith("/protocol/openid-connect" + TOKEN_SUFFIX)
        ? Optional.of(
            tokenEndpoint.substring(0, tokenEndpoint.length() - TOKEN_SUFFIX.length()) + "/logout")
        : Optional.empty();
  }
}
