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
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

/**
 * The issuer's endpoints, read from its discovery document when they are first needed and not at
 * start-up: the backend may start before the identity provider. Readiness (the separate {@link
 * IdentityDiscoveryHealthIndicator}) keeps traffic away until the provider has published the
 * configured issuer and while it publishes another one; it does not look at the endpoints, so a
 * document this class refuses for them (missing, not http, plaintext where plaintext was not
 * allowed) leaves the backend ready. Before a first document was accepted, every sign-in step then
 * answers "unavailable". After that, a refused document is treated like a read that failed: the
 * last accepted endpoints keep being used, as the next paragraph says. (A document that names
 * another issuer also makes the backend unready, which is the health indicator's doing.)
 *
 * <p>A document is accepted only when it publishes exactly the configured issuer and http(s)
 * endpoints. An accepted document is used for {@link #KEPT} and then read again. When that read
 * fails, or the document it returns is refused, the last accepted document keeps being used and the
 * read is tried again after {@link #RETRY}, without a limit on how long: a provider that is briefly
 * away or wrong must not turn requests of sessions that are still valid into outages. Until a first
 * document was accepted, every failure is an {@link IdentityProviderUnavailableException}: callers
 * answer 5xx and nothing from the provider's answer reaches a response. That failure is kept for
 * {@link #RETRY} too and answered to every caller in the interval. Anybody can cause a read by
 * presenting a credential, so however many arrive, the provider receives one discovery request per
 * {@link #RETRY} while its document is not accepted, and concurrent callers share the request in
 * flight.
 *
 * <p>Every read that does not give an accepted document is logged as a warning. While the earlier
 * endpoints stay in use that warning is the only signal an operator gets, so a refused document is
 * logged with a fixed reason code and the field it was refused for ({@link #reason}).
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
    this(client, properties, kept, retry, Schedulers.parallel());
  }

  /**
   * The intervals are expired, and the read is timed out, by {@code timer}. Production uses the
   * parallel scheduler; a test passes a virtual clock and moves it.
   */
  IdentityDiscovery(
      WebClient client,
      IdentityProperties properties,
      Duration kept,
      Duration retry,
      Scheduler timer) {
    this.properties = properties;
    this.metadata =
        Mono.defer(() ->
                client
                    .get()
                    .uri(properties.discoveryUri())
                    .retrieve()
                    .bodyToMono(DOCUMENT)
                    .timeout(TIMEOUT, timer)
                    .map(this::accept)
                    .switchIfEmpty(Mono.error(() -> new RefusedDocument(Refusal.EMPTY, null))))
            .doOnNext(lastAccepted::set)
            .map(accepted -> new Read(accepted, true))
            .onErrorResume(failure -> {
              log.warn("Identity discovery failed: {}", reason(failure));
              ProviderMetadata earlier = lastAccepted.get();
              return earlier != null
                  ? Mono.just(new Read(earlier, false))
                  : Mono.error(new IdentityProviderUnavailableException(failure));
            })
            .cache(
                read -> read.fresh() ? kept : retry, failure -> retry, () -> Duration.ZERO, timer)
            .map(Read::metadata);
  }

  /** The accepted endpoints, or an {@link IdentityProviderUnavailableException}. */
  public Mono<ProviderMetadata> metadata() {
    return metadata;
  }

  private ProviderMetadata accept(Map<String, Object> document) {
    if (!properties.issuerUri().equals(document.get("issuer"))) {
      throw new RefusedDocument(Refusal.ISSUER_MISMATCH, "issuer");
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
      throw new RefusedDocument(Refusal.ENDPOINT_MISSING, name);
    }
    URI parsed;
    try {
      parsed = URI.create(value);
    } catch (IllegalArgumentException unparsable) {
      throw new RefusedDocument(Refusal.ENDPOINT_NOT_HTTP, name);
    }
    String scheme = parsed.getScheme() == null ? "" : parsed.getScheme().toLowerCase(Locale.ROOT);
    if (parsed.getHost() == null || !(scheme.equals("http") || scheme.equals("https"))) {
      throw new RefusedDocument(Refusal.ENDPOINT_NOT_HTTP, name);
    }
    if (scheme.equals("http") && !plaintext) {
      throw new RefusedDocument(Refusal.ENDPOINT_PLAINTEXT, name);
    }
    return value;
  }

  /**
   * What the warning says about a read that did not give an accepted document. A refused document
   * is named by its reason code and the field it was refused for, both fixed text of this class;
   * nothing the provider published is logged. Any other failure (no connection, no answer in time,
   * a status, a body that is not JSON) is named by its exception classes only (NFR-6).
   */
  static String reason(Throwable failure) {
    return failure instanceof RefusedDocument refused
        ? refused.getMessage()
        : SafeFailure.describe(failure);
  }

  /** Why a document that was read is not accepted. */
  enum Refusal {
    /** The answer had no body. */
    EMPTY,
    /** The published issuer is not the configured one. */
    ISSUER_MISMATCH,
    /** A required endpoint is absent or not a string. */
    ENDPOINT_MISSING,
    /** An endpoint is not an absolute http(s) URL with a host. */
    ENDPOINT_NOT_HTTP,
    /** An endpoint is plaintext where the address it belongs to may not be. */
    ENDPOINT_PLAINTEXT
  }

  /** A discovery document this class refuses; the message is the reason code and the field. */
  static final class RefusedDocument extends IllegalStateException {

    private static final long serialVersionUID = 1L;

    RefusedDocument(Refusal refusal, String field) {
      super(
          field == null
              ? "document refused, " + refusal
              : "document refused, " + refusal + " (" + field + ")");
    }
  }
}
