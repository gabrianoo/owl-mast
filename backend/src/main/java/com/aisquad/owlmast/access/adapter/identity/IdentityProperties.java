package com.aisquad.owlmast.access.adapter.identity;

import java.net.URI;
import java.util.Locale;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

/**
 * The OpenID Connect issuer this installation trusts. Required: there is no configuration that runs
 * Owl Mast without an identity provider, bundled or external (AC2).
 *
 * <p>The issuer is kept exactly as configured (surrounding whitespace aside): OpenID Connect
 * Discovery 1.0 section 4.3 and the token {@code iss} check compare issuers as exact strings, so a
 * trailing slash is part of the identifier and is never normalised away.
 *
 * <p>A plaintext {@code http} issuer is refused unless {@code allowInsecureIssuer} is set:
 * discovery and signing keys fetched over plaintext can be substituted in transit. The installation
 * chart sets the flag only for the cluster-local bundled Keycloak or an explicit operator opt-in;
 * the rule lives here as well so that it holds for every deployment path, not only for the chart.
 *
 * <p>{@code backchannelUri} (OM-02.01, optional) is where the backend itself reaches the issuer
 * when that is not the issuer's own address: the bundled Keycloak publishes its public origin as
 * the issuer, which the browser uses, while the backend talks to the cluster-local Service. It only
 * says where the discovery document is fetched; the document must still publish exactly {@code
 * issuerUri}, and tokens are still checked against {@code issuerUri}. It follows the same syntax
 * rules and has its own plaintext opt-in. Absent means the issuer.
 */
@ConfigurationProperties("owlmast.identity")
public record IdentityProperties(
    String issuerUri,
    boolean allowInsecureIssuer,
    String backchannelUri,
    boolean allowInsecureBackchannel) {

  private static final String PROPERTY = "owlmast.identity.issuer-uri";
  private static final String INSECURE_PROPERTY = "owlmast.identity.allow-insecure-issuer";
  private static final String BACKCHANNEL_PROPERTY = "owlmast.identity.backchannel-uri";
  private static final String INSECURE_BACKCHANNEL_PROPERTY =
      "owlmast.identity.allow-insecure-backchannel";
  private static final int MAX_PORT = 65_535;

  @ConstructorBinding
  public IdentityProperties {
    if (issuerUri == null || issuerUri.isBlank()) {
      throw new IllegalArgumentException(
          PROPERTY
              + " is required: set it to the bundled Keycloak realm or a compatible external"
              + " issuer; disabling the identity bundle never disables authentication");
    }
    issuerUri = issuerUri.strip();
    requireLocation(issuerUri, PROPERTY, INSECURE_PROPERTY, allowInsecureIssuer);
    backchannelUri =
        backchannelUri == null || backchannelUri.isBlank() ? null : backchannelUri.strip();
    if (backchannelUri != null) {
      requireLocation(
          backchannelUri,
          BACKCHANNEL_PROPERTY,
          INSECURE_BACKCHANNEL_PROPERTY,
          allowInsecureBackchannel);
    }
  }

  /** An issuer the backend reaches on its own address. */
  public IdentityProperties(String issuerUri, boolean allowInsecureIssuer) {
    this(issuerUri, allowInsecureIssuer, null, false);
  }

  private static void requireLocation(
      String value, String property, String insecureProperty, boolean allowInsecure) {
    URI parsed = URI.create(value);
    if (!parsed.isAbsolute() || parsed.getHost() == null) {
      throw new IllegalArgumentException(property + " must be an absolute URL with a host");
    }
    String scheme = parsed.getScheme().toLowerCase(Locale.ROOT);
    if (!scheme.equals("http") && !scheme.equals("https")) {
      throw new IllegalArgumentException(property + " must use http or https");
    }
    if (scheme.equals("http") && !allowInsecure) {
      throw new IllegalArgumentException(
          property
              + " must use https: discovery and signing keys could be substituted in transit. Set "
              + insecureProperty
              + "=true to accept a plaintext issuer explicitly (cluster-local or disposable"
              + " fixtures only)");
    }
    // -1 means no port was given; an explicit port must be one a connection can be opened to.
    if (parsed.getPort() == 0 || parsed.getPort() > MAX_PORT) {
      throw new IllegalArgumentException(property + " must use a port between 1 and 65535");
    }
    if (parsed.getRawUserInfo() != null) {
      throw new IllegalArgumentException(property + " must not contain user info");
    }
    if (parsed.getRawQuery() != null || parsed.getRawFragment() != null) {
      throw new IllegalArgumentException(
          property
              + " must not contain a query or fragment: the discovery document is resolved below"
              + " the issuer path");
    }
  }

  /**
   * Discovery document location per OpenID Connect Discovery 1.0 section 4: any terminating slash
   * of the issuer is removed before the well-known path is appended. Only this location is
   * normalised; the issuer itself is compared verbatim. With a back-channel address the document is
   * fetched there.
   */
  public URI discoveryUri() {
    String location = backchannelUri != null ? backchannelUri : issuerUri;
    String base = location.endsWith("/") ? location.substring(0, location.length() - 1) : location;
    return URI.create(base + "/.well-known/openid-configuration");
  }
}
