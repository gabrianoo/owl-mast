package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.adapter.identity.IdentityDiscovery;
import com.aisquad.owlmast.access.adapter.identity.SignInProperties;
import com.aisquad.owlmast.access.application.SessionLedger;
import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.access.domain.SessionEnd;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import org.springframework.web.server.session.InMemoryWebSessionStore;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * The life of a signed-in session after sign-in (OM-02.01). The session lives in this process's
 * memory; its lifetime is the identity provider's:
 *
 * <ul>
 *   <li>on every request the tokens the backend holds are checked, and renewed with the refresh
 *       token once the access token is about to expire. A renewal the provider refuses means the
 *       provider's session is over (its lifetime passed, the person signed out elsewhere, an
 *       administrator ended it): the session ends here and the request is anonymous. Nothing is
 *       answered from an earlier state;
 *   <li>a provider that cannot be reached is not a refusal: the session is kept and the request is
 *       not served ({@link Standing#UNVERIFIABLE});
 *   <li>the provider's back-channel logout notice ends the named sessions at once;
 *   <li>sign-out ends the session here and asks the provider to end its own;
 *   <li>a session the store dropped (idle for {@link #MEMORY_BOUND}) is noticed by {@link #sweep}.
 * </ul>
 *
 * <p>Every end removes the registry entry first and is recorded once through the ledger.
 */
@Slf4j
final class SessionKeeper {

  /** What a request's session is worth right now. */
  enum Standing {
    /** The provider still stands behind the session. */
    CURRENT,
    /** The session is over; the request continues without it. */
    ENDED,
    /** The provider could not be asked; the session is kept, the request is not served. */
    UNVERIFIABLE
  }

  /** Whether the identity provider confirmed that its own session ended at sign-out. */
  enum ProviderSession {
    ENDED,
    UNCONFIRMED
  }

  /**
   * How long an idle signed-in session is kept in memory. It bounds memory, not the session: the
   * realm's own lifetimes end a session earlier, at the next request. It is longer than Keycloak's
   * default maximum session (10 hours), so with default realm settings the realm always decides.
   */
  static final Duration MEMORY_BOUND = Duration.ofHours(12);

  /** How long a sign-in that was started and not finished keeps its state. */
  static final Duration PENDING_SIGN_IN = Duration.ofMinutes(5);

  static final Duration SWEEP_INTERVAL = Duration.ofMinutes(1);
  static final Duration PROVIDER_LOGOUT_TIMEOUT = Duration.ofSeconds(5);

  /** Token-endpoint answers that refuse this backend as a client, whatever the session. */
  private static final Set<String> CLIENT_CODES =
      Set.of(OAuth2ErrorCodes.INVALID_CLIENT, OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);

  private final InMemoryWebSessionStore store;
  private final SessionRegistry registry;
  private final SessionLedger ledger;
  private final ReactiveOAuth2AuthorizedClientManager authorizedClients;
  private final ServerOAuth2AuthorizedClientRepository authorizedClientRepository;
  private final IdentityDiscovery discovery;
  private final SignInProperties properties;
  private final WebClient providerClient;
  private final Clock clock;
  private final ConcurrentHashMap<String, Mono<Standing>> checksInFlight =
      new ConcurrentHashMap<>();
  private final AtomicLong lastSweepMillis = new AtomicLong();

  SessionKeeper(
      InMemoryWebSessionStore store,
      SessionRegistry registry,
      SessionLedger ledger,
      ReactiveOAuth2AuthorizedClientManager authorizedClients,
      ServerOAuth2AuthorizedClientRepository authorizedClientRepository,
      IdentityDiscovery discovery,
      SignInProperties properties,
      WebClient providerClient,
      Clock clock) {
    this.store = store;
    this.registry = registry;
    this.ledger = ledger;
    this.authorizedClients = authorizedClients;
    this.authorizedClientRepository = authorizedClientRepository;
    this.discovery = discovery;
    this.properties = properties;
    this.providerClient = providerClient;
    this.clock = clock;
  }

  /**
   * Called once a sign-in has completed and its session is authenticated. A sign-in that completes
   * in a browser session somebody was already signed in with (two tabs that both started one) takes
   * the earlier one's place, and the earlier one is recorded as ended.
   */
  Mono<Void> started(WebSession session, SignedInPerson person) {
    session.setMaxIdleTime(MEMORY_BOUND);
    List<SessionRegistry.Entry> replaced = registry.heldBy(session);
    registry.register(SessionRegistry.Entry.of(session, person));
    return Flux.fromIterable(replaced)
        .concatMap(earlier ->
            Mono.justOrEmpty(registry.remove(earlier.sessionRef()))
                .flatMap(entry ->
                    ledger.ended(entry.principal(), entry.sessionRef(), SessionEnd.REPLACED)))
        .then();
  }

  /**
   * Whether the provider still stands behind the session of this request. Concurrent requests of
   * one session share one check, so a renewal is asked for once.
   */
  Mono<Standing> standing(
      ServerWebExchange exchange, WebSession session, OAuth2AuthenticationToken authentication) {
    String sessionId = session.getId();
    return checksInFlight.computeIfAbsent(
        sessionId,
        id ->
            Mono.defer(() -> check(exchange, session, authentication))
                .doFinally(signal -> checksInFlight.remove(id))
                .cache());
  }

  private Mono<Standing> check(
      ServerWebExchange exchange, WebSession session, OAuth2AuthenticationToken authentication) {
    OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId(
                DiscoveredClientRegistrations.REGISTRATION_ID)
            .principal(authentication)
            .attribute(ServerWebExchange.class.getName(), exchange)
            .build();
    Optional<SignedInPerson> person =
        authentication.getPrincipal() instanceof SignedInPerson signedIn
            ? Optional.of(signedIn)
            : Optional.empty();
    return authorizedClients
        .authorize(request)
        // A provider that never answers the renewal is an outage: the session is kept.
        .timeout(CredentialValidation.PROVIDER_TIMEOUT)
        .map(this::stillValid)
        .defaultIfEmpty(false)
        .flatMap(valid ->
            valid && person.isPresent()
                ? Mono.just(Standing.CURRENT)
                : end(session, person, SessionEnd.EXPIRED).thenReturn(Standing.ENDED))
        .onErrorResume(failure -> {
          if (refused(failure)) {
            log.info(
                "{}The identity provider no longer renews the session: {}",
                exchange.getLogPrefix(),
                SafeFailure.describe(failure));
            return end(session, person, SessionEnd.EXPIRED).thenReturn(Standing.ENDED);
          }
          if (failure instanceof OAuth2AuthorizationException authorization
              && CLIENT_CODES.contains(authorization.getError().getErrorCode())) {
            // The provider refused this backend, not the session: a wrong client secret must not
            // sign everybody out as "expired". It needs an operator.
            log.error(
                "{}The identity provider refused the backend's client credentials; sessions"
                    + " cannot be renewed until the client configuration is corrected: {}",
                exchange.getLogPrefix(),
                SafeFailure.describe(failure));
          } else {
            log.warn(
                "{}Session could not be verified with the identity provider: {}",
                exchange.getLogPrefix(),
                SafeFailure.describe(failure));
          }
          return Mono.just(Standing.UNVERIFIABLE);
        });
  }

  /** An access token past its expiry that was not renewed (no refresh token) ends the session. */
  private boolean stillValid(OAuth2AuthorizedClient client) {
    Instant expiresAt = client.getAccessToken().getExpiresAt();
    return expiresAt == null || expiresAt.isAfter(clock.instant());
  }

  /**
   * Only a refusal of the grant ({@code invalid_grant}: the refresh token is expired, revoked or
   * belongs to an ended session) says the provider's session is over. Every other answer, a
   * rejected client included, leaves the session unverifiable.
   */
  private static boolean refused(Throwable failure) {
    return failure instanceof OAuth2AuthorizationException authorization
        && OAuth2ErrorCodes.INVALID_GRANT.equals(authorization.getError().getErrorCode());
  }

  /** Ends the session of this request for the given reason; a session already ended stays so. */
  private Mono<Void> end(WebSession session, Optional<SignedInPerson> person, SessionEnd why) {
    Optional<SessionRegistry.Entry> entry =
        person.flatMap(signedIn -> registry.remove(signedIn.sessionRef()));
    return session
        .invalidate()
        .then(
            Mono.defer(() ->
                entry
                    .map(known -> ledger.ended(known.principal(), known.sessionRef(), why))
                    .orElseGet(Mono::empty)));
  }

  /**
   * Sign-out: the session ends here whatever the provider answers; the provider is then asked to
   * end its own session with the refresh token the backend holds, so no token goes through the
   * browser.
   */
  Mono<ProviderSession> signOut(
      ServerWebExchange exchange, WebSession session, OAuth2AuthenticationToken authentication) {
    return authorizedClientRepository
        .<OAuth2AuthorizedClient>loadAuthorizedClient(
            DiscoveredClientRegistrations.REGISTRATION_ID, authentication, exchange)
        .mapNotNull(OAuth2AuthorizedClient::getRefreshToken)
        .map(refreshToken -> refreshToken.getTokenValue())
        .map(Optional::of)
        .defaultIfEmpty(Optional.empty())
        .onErrorReturn(Optional.empty())
        .flatMap(refreshToken ->
            end(
                    session,
                    Optional.ofNullable(authentication.getPrincipal())
                        .filter(SignedInPerson.class::isInstance)
                        .map(SignedInPerson.class::cast),
                    SessionEnd.SIGNED_OUT)
                .then(
                    Mono.defer(() ->
                        refreshToken
                            .map(this::endProviderSession)
                            .orElseGet(() -> Mono.just(ProviderSession.UNCONFIRMED)))));
  }

  private Mono<ProviderSession> endProviderSession(String refreshToken) {
    return discovery
        .metadata()
        .flatMap(metadata -> Mono.justOrEmpty(metadata.logoutEndpoint()))
        .flatMap(endpoint ->
            providerClient
                .post()
                .uri(endpoint)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(
                    BodyInserters.fromFormData("client_id", properties.clientId())
                        .with("client_secret", properties.clientSecret())
                        .with("refresh_token", refreshToken))
                .retrieve()
                .toBodilessEntity()
                .timeout(PROVIDER_LOGOUT_TIMEOUT)
                .thenReturn(ProviderSession.ENDED))
        .defaultIfEmpty(ProviderSession.UNCONFIRMED)
        .onErrorResume(failure -> {
          log.warn(
              "The identity provider did not confirm the end of its session: {}",
              SafeFailure.describe(failure));
          return Mono.just(ProviderSession.UNCONFIRMED);
        });
  }

  /** The provider announced that sessions ended; returns how many ended here. */
  Mono<Long> revoke(ExternalIdentity identity, Optional<String> providerSessionId) {
    return Flux.fromIterable(registry.matching(identity, providerSessionId))
        .concatMap(matched ->
            Mono.justOrEmpty(registry.remove(matched.sessionRef()))
                .flatMap(entry ->
                    entry
                        .session()
                        .invalidate()
                        .then(
                            ledger.ended(entry.principal(), entry.sessionRef(), SessionEnd.REVOKED))
                        .thenReturn(entry.sessionRef())))
        .count();
  }

  /**
   * Records the sessions the store dropped because they were idle for {@link #MEMORY_BOUND}. It
   * runs with requests, at most once per {@link #SWEEP_INTERVAL}: there is no timer of its own, so
   * an idle backend records such an end with its next request.
   */
  Mono<Void> sweep() {
    long now = clock.millis();
    long last = lastSweepMillis.get();
    if (now - last < SWEEP_INTERVAL.toMillis() || !lastSweepMillis.compareAndSet(last, now)) {
      return Mono.empty();
    }
    store.removeExpiredSessions();
    return Flux.fromIterable(registry.expired())
        .concatMap(expired ->
            Mono.justOrEmpty(registry.remove(expired.sessionRef()))
                .flatMap(entry ->
                    ledger.ended(entry.principal(), entry.sessionRef(), SessionEnd.EXPIRED)))
        .then();
  }
}
