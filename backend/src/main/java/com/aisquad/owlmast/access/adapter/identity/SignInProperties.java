package com.aisquad.owlmast.access.adapter.identity;

import java.net.URI;
import java.util.Locale;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Browser sign-in settings (OM-02.01, docs/identity.md). All of {@code clientId}, {@code
 * clientSecret} and {@code applicationOrigin} are required: there is no configuration that starts
 * the backend without sign-in.
 *
 * <p>{@code applicationOrigin} is the one public origin that serves the shell and this backend. The
 * redirect back from the identity provider and every redirect to the shell are built from it, never
 * from request headers. It must be https; plain http is accepted only for a loopback host, where
 * browsers still accept the Secure session cookie.
 *
 * <p>{@code audience} is what a bearer credential's {@code aud} must contain; absent means the
 * client id. {@code tenant} is the tenant of every signed-in principal until OM-02.02.
 */
@ConfigurationProperties("owlmast.sign-in")
public record SignInProperties(
    String clientId,
    String clientSecret,
    String applicationOrigin,
    String audience,
    String tenant) {

  private static final String PREFIX = "owlmast.sign-in.";
  private static final Set<String> LOOPBACK_HOSTS = Set.of("localhost", "127.0.0.1", "[::1]");

  public SignInProperties {
    clientId = required(clientId, "client-id");
    if (clientSecret == null || clientSecret.isBlank()) {
      throw new IllegalArgumentException(
          PREFIX
              + "client-secret is required: the backend is a confidential client of the identity"
              + " provider");
    }
    // A secret read from a file often ends with a line end, which every exchange would refuse.
    clientSecret = clientSecret.strip();
    applicationOrigin = requireOrigin(required(applicationOrigin, "application-origin"));
    audience = audience == null || audience.isBlank() ? clientId : audience.strip();
    tenant = required(tenant, "tenant");
  }

  /** {@code applicationOrigin} plus an absolute path. */
  public String applicationUrl(String path) {
    return applicationOrigin + path;
  }

  /** The secret is never part of a log line or an error message. */
  @Override
  public String toString() {
    return "SignInProperties[clientId="
        + clientId
        + ", applicationOrigin="
        + applicationOrigin
        + ", audience="
        + audience
        + ", tenant="
        + tenant
        + "]";
  }

  private static String required(String value, String name) {
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(
          PREFIX + name + " is required: there is no configuration without sign-in");
    }
    return value.strip();
  }

  private static String requireOrigin(String value) {
    String property = PREFIX + "application-origin";
    URI parsed;
    try {
      parsed = URI.create(value);
    } catch (IllegalArgumentException malformed) {
      throw new IllegalArgumentException(property + " must be an origin such as https://host");
    }
    if (!parsed.isAbsolute() || parsed.getHost() == null) {
      throw new IllegalArgumentException(property + " must be an origin such as https://host");
    }
    String scheme = parsed.getScheme().toLowerCase(Locale.ROOT);
    boolean loopback = LOOPBACK_HOSTS.contains(parsed.getHost().toLowerCase(Locale.ROOT));
    if (!scheme.equals("https") && !(scheme.equals("http") && loopback)) {
      throw new IllegalArgumentException(
          property
              + " must use https: the session cookie is Secure. Plain http is accepted only for a"
              + " loopback host");
    }
    if (parsed.getRawUserInfo() != null
        || parsed.getRawQuery() != null
        || parsed.getRawFragment() != null
        || !(parsed.getRawPath() == null || parsed.getRawPath().isEmpty())) {
      throw new IllegalArgumentException(
          property + " must be an origin only: no user info, path, query or fragment");
    }
    return value;
  }
}
