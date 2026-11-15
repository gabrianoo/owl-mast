package com.aisquad.owlmast.access.adapter.identity;

import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.net.URI;
import java.time.Duration;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

/**
 * The issuer's endpoints, read from its discovery document when they are first needed and not at
 * start-up: the backend may start before the identity provider. Readiness (the separate {@link
 * IdentityDiscoveryHealthIndicator}) keeps traffic away while the provider does not answer or
 * publishes another issuer; it does not look at the endpoints, so a document this class refuses for
 * them (missing, not http, plaintext where plaintext was not allowed) leaves the backend ready and
 * every sign-in step answering "unavailable".
 *
 * <p>A document is accepted only when it publishes exactly the configured issuer and http(s)
 * endpoints. An accepted document is used for {@link #KEPT} and then read again. When that read
 * fails, the last accepted document keeps being used and the read is tried again after {@link
 * #RETRY}: a provider that is briefly away must not turn requests of sessions that are still valid
 * into outages. Until a first document was accepted, every failure is an {@link
 * IdentityProviderUnavailableException}, which is never kept: callers answer 5xx and nothing from
 * the provider's answer reaches a response.
 */
@Slf4j
public final class IdentityDiscovery {

  static final Duration TIMEOUT = Duration.ofSeconds(3);
  static final Duration KEPT = Duration.ofMinutes(5);
  static final Duration RETRY = Duration.ofSeconds(5);
  private static final ParameterizedTypeReference<Map<String, Object>> DOCUMENT =
      new ParameterizedTypeReference<>() {};

  /** A document and whether it was just read (kept for {@link #KEPT}) or is the earlier one. */
  private record Read(ProviderMetadata metadata, boolean fresh) {}

  private final IdentityProperties properties;
  private final AtomicReference<ProviderMetadata> lastAccepted = new AtomicReference<>();
  private final Mono<ProviderMetadata> metadata;

  public IdentityDiscovery(WebClient client, IdentityProperties properties) {
    this(client, properties, KEPT, RETRY);
  }

  IdentityDiscovery(
      WebClient client, IdentityProperties properties, Duration kept, Duration retry) {
    this.properties = properties;
    this.metadata =
        Mono.defer(() ->
                client
                    .get()
                    .uri(properties.discoveryUri())
                    .retrieve()
                    .bodyToMono(DOCUMENT)
                    .timeout(TIMEOUT)
                    .map(this::accept)
                    .switchIfEmpty(
                        Mono.error(() -> new IllegalStateException("empty discovery answer"))))
            .doOnNext(lastAccepted::set)
            .map(accepted -> new Read(accepted, true))
            .onErrorResume(failure -> {
              log.warn("Identity discovery failed: {}", SafeFailure.describe(failure));
              ProviderMetadata earlier = lastAccepted.get();
              return earlier != null
                  ? Mono.just(new Read(earlier, false))
                  : Mono.error(new IdentityProviderUnavailableException(failure));
            })
            .cache(
                read -> read.fresh() ? kept : retry, failure -> Duration.ZERO, () -> Duration.ZERO)
            .map(Read::metadata);
  }

  /** The accepted endpoints, or an {@link IdentityProviderUnavailableException}. */
  public Mono<ProviderMetadata> metadata() {
    return metadata;
  }

  private ProviderMetadata accept(Map<String, Object> document) {
    if (!properties.issuerUri().equals(document.get("issuer"))) {
      throw new IllegalStateException("the published issuer differs from the configured issuer");
    }
    // The browser's endpoint may be plaintext only where the issuer may be; the backend's own
    // endpoints only where the address the backend uses may be.
    boolean plaintextBackchannel =
        properties.backchannelUri() != null
            ? properties.allowInsecureBackchannel()
            : properties.allowInsecureIssuer();
    return new ProviderMetadata(
        properties.issuerUri(),
        endpoint(document, "authorization_endpoint", properties.allowInsecureIssuer()),
        endpoint(document, "token_endpoint", plaintextBackchannel),
        endpoint(document, "jwks_uri", plaintextBackchannel));
  }

  private static String endpoint(Map<String, Object> document, String name, boolean plaintext) {
    if (!(document.get(name) instanceof String value)) {
      throw new IllegalStateException("the discovery document has no " + name);
    }
    URI parsed = URI.create(value);
    String scheme = parsed.getScheme() == null ? "" : parsed.getScheme().toLowerCase(Locale.ROOT);
    if (parsed.getHost() == null || !(scheme.equals("http") || scheme.equals("https"))) {
      throw new IllegalStateException("the discovery document's " + name + " is not an http URL");
    }
    if (scheme.equals("http") && !plaintext) {
      throw new IllegalStateException("the discovery document's " + name + " is plaintext");
    }
    return value;
  }
}
