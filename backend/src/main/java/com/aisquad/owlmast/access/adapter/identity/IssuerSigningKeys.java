package com.aisquad.owlmast.access.adapter.identity;

import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKMatcher;
import com.nimbusds.jose.jwk.JWKSelector;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jwt.SignedJWT;
import java.text.ParseException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

/**
 * The issuer's signing keys (its JWK set), for verifying a credential that anybody can present: a
 * bearer credential or a logout notice. The header of such a token is the caller's choice, so the
 * identity provider is asked for its keys at a bounded rate, whatever the tokens name:
 *
 * <ul>
 *   <li>A token whose key is held is served from the held set, without a request.
 *   <li>A token whose key is not held (or no set is held yet) causes a fetch, and for {@link #KEPT}
 *       after that fetch every such token is answered from its result: a key the set still does not
 *       hold yields no key, so the token is refused. After a fetch that succeeded the provider
 *       therefore receives no key request for {@link #KEPT}, and a signing key it starts using is
 *       accepted at most that much later. Anybody can cause the fetch that starts the interval, by
 *       presenting a token that names an unknown key.
 *   <li>A fetch that fails is an {@link IdentityProviderUnavailableException}, an outage and never
 *       a refusal. It is answered to every token that needs a fetch for {@link #RETRY}, then the
 *       fetch is tried again: a key endpoint that keeps failing is asked once per {@link #RETRY}
 *       while such tokens arrive. Tokens whose key is held keep being verified meanwhile.
 * </ul>
 *
 * <p>The held set is replaced only by a later fetch. The key endpoint is the one the accepted
 * discovery document names; when that address changes, the keys held for the earlier one are
 * dropped.
 */
@Slf4j
public final class IssuerSigningKeys {

  static final Duration KEPT = Duration.ofSeconds(30);
  static final Duration RETRY = Duration.ofSeconds(5);

  /** How long the identity provider may take to answer with its keys. */
  static final Duration FETCH_TIMEOUT = Duration.ofSeconds(10);

  /** The keys of one key endpoint: the set last fetched and the fetch shared by its callers. */
  private record Source(String jwksUri, AtomicReference<JWKSet> held, Mono<JWKSet> fetched) {}

  private final WebClient client;
  private final Mono<String> jwksUri;
  private final Duration kept;
  private final Duration retry;
  private final Duration fetchTimeout;
  private final Scheduler timer;
  private final AtomicReference<Source> source = new AtomicReference<>();

  public IssuerSigningKeys(WebClient client, IdentityDiscovery discovery) {
    this(
        client,
        discovery.metadata().map(ProviderMetadata::jwksUri),
        KEPT,
        RETRY,
        FETCH_TIMEOUT,
        Schedulers.parallel());
  }

  /**
   * The intervals are expired, and the fetch is timed out, by {@code timer}. Production uses the
   * parallel scheduler; a test passes a virtual clock and moves it.
   */
  IssuerSigningKeys(
      WebClient client,
      Mono<String> jwksUri,
      Duration kept,
      Duration retry,
      Duration fetchTimeout,
      Scheduler timer) {
    this.client = client;
    this.jwksUri = jwksUri;
    this.kept = kept;
    this.retry = retry;
    this.fetchTimeout = fetchTimeout;
    this.timer = timer;
  }

  /**
   * Completes when the issuer's key endpoint is known, that is when a discovery document was
   * accepted; an {@link IdentityProviderUnavailableException} otherwise. Without an accepted
   * document nothing presented can be judged, whatever it looks like.
   */
  public Mono<Void> located() {
    return jwksUri.then();
  }

  /**
   * The keys that may have signed {@code token}: none when the issuer has no such key, an {@link
   * IdentityProviderUnavailableException} when the keys are needed and cannot be fetched.
   */
  public Flux<JWK> of(SignedJWT token) {
    JWKMatcher matcher = JWKMatcher.forJWSHeader(token.getHeader());
    if (matcher == null) {
      // An algorithm no key can verify: nothing to look for, and nothing to ask the provider.
      return Flux.empty();
    }
    JWKSelector selector = new JWKSelector(matcher);
    return jwksUri.flatMapMany(uri -> {
      Source current = sourceOf(uri);
      JWKSet held = current.held().get();
      List<JWK> known = held == null ? List.of() : selector.select(held);
      return known.isEmpty()
          ? current.fetched().flatMapIterable(selector::select)
          : Flux.fromIterable(known);
    });
  }

  private Source sourceOf(String uri) {
    return source.updateAndGet(
        current -> current != null && current.jwksUri().equals(uri) ? current : newSource(uri));
  }

  private Source newSource(String uri) {
    AtomicReference<JWKSet> held = new AtomicReference<>();
    Mono<JWKSet> fetched =
        Mono.defer(() ->
                client
                    .get()
                    .uri(uri)
                    .retrieve()
                    .bodyToMono(String.class)
                    .timeout(fetchTimeout, timer)
                    .map(IssuerSigningKeys::parse)
                    .switchIfEmpty(
                        Mono.error(() -> new IllegalStateException("empty key set answer"))))
            .doOnNext(held::set)
            .onErrorMap(failure -> {
              // Class names only: the answer may echo configuration.
              log.warn("Fetching the issuer's keys failed: {}", SafeFailure.describe(failure));
              return new IdentityProviderUnavailableException(failure);
            })
            .cache(keys -> kept, failure -> retry, () -> Duration.ZERO, timer);
    return new Source(uri, held, fetched);
  }

  private static JWKSet parse(String document) {
    try {
      return JWKSet.parse(document);
    } catch (ParseException unusable) {
      // The parser's message can quote the document: only the fact is carried on.
      throw new IllegalStateException("the key set answer is not a JWK set");
    }
  }
}
