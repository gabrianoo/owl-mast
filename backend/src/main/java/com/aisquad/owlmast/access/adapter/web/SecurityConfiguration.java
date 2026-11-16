package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.adapter.identity.IdentityDiscovery;
import com.aisquad.owlmast.access.adapter.identity.IdentityProperties;
import com.aisquad.owlmast.access.adapter.identity.IssuerSigningKeys;
import com.aisquad.owlmast.access.adapter.identity.SignInProperties;
import com.aisquad.owlmast.access.adapter.persistence.R2dbcPrincipalStore;
import com.aisquad.owlmast.access.application.SessionLedger;
import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.access.port.PrincipalStore;
import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.TenantId;
import com.aisquad.owlmast.platform.web.ProblemResponses;
import java.time.Clock;
import java.time.Duration;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.oidc.authentication.OidcAuthorizationCodeReactiveAuthenticationManager;
import org.springframework.security.oauth2.client.oidc.authentication.ReactiveOidcIdTokenDecoderFactory;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.DefaultServerOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.server.WebSessionServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.csrf.CsrfWebFilter;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;
import org.springframework.security.web.server.util.matcher.AndServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.NegatedServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.OrServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher.MatchResult;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.adapter.WebHttpHandlerBuilder;
import org.springframework.web.server.session.DefaultWebSessionManager;
import org.springframework.web.server.session.InMemoryWebSessionStore;
import org.springframework.web.server.session.WebSessionIdResolver;
import org.springframework.web.server.session.WebSessionManager;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

/**
 * Authentication of every request (OM-02.01, docs/identity.md). There is one filter chain and no
 * setting that removes it.
 *
 * <ul>
 *   <li><b>Browser:</b> the backend is a confidential OpenID Connect client (authorization code
 *       with PKCE). Tokens stay in the backend; the browser holds one HttpOnly, Secure,
 *       SameSite=Lax cookie naming a session kept in this process's memory.
 *   <li><b>Bearer:</b> a credential in the {@code Authorization} header is verified against the
 *       issuer's keys and checked for expiry, issuer and audience.
 *   <li>Either way the principal is the one bound to the credential's issuer and subject, and its
 *       scope is bound into the Reactor Context after authorization.
 *   <li><b>Public:</b> the compatibility descriptor, the health endpoints, the session read and the
 *       sign-in and logout-notice endpoints. Everything else needs an authenticated principal: an
 *       API call without one answers 401 in the problem-details envelope with the challenge and is
 *       never redirected to a login page.
 *   <li><b>CSRF:</b> an unsafe method needs the token of the session, sent back in a header. The
 *       exceptions carry no ambient authority: a bearer call, and the identity provider's logout
 *       notice, which is authenticated by its own signed token.
 *   <li>No CORS configuration: shell and backend share one origin.
 * </ul>
 *
 * <p>The condition is the framework's own: these beans need the reactive web server. The backend is
 * always started as one; a start without any web server (a migration-only tool run) serves no
 * request and so has nothing to authenticate.
 */
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
@Slf4j
@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableConfigurationProperties(SignInProperties.class)
class SecurityConfiguration {

  static final String BEARER_PREFIX = "bearer ";

  @Bean
  IdentityDiscovery providerDiscovery(IdentityProperties properties) {
    return new IdentityDiscovery(WebClient.create(), properties);
  }

  /**
   * The issuer's signing keys, one instance for the bearer and the logout-token decoder: both take
   * tokens from anybody, and the bound on key fetches holds across them only when it is shared.
   */
  @Bean
  IssuerSigningKeys issuerSigningKeys(IdentityDiscovery discovery) {
    return new IssuerSigningKeys(WebClient.create(), discovery);
  }

  @Bean
  PrincipalStore principalStore(DatabaseClient client) {
    return new R2dbcPrincipalStore(client);
  }

  @Bean
  SessionLedger sessionLedger(
      AuditedMutations mutations,
      ScopedTransactions transactions,
      PrincipalStore principals,
      SignInProperties properties) {
    return new SessionLedger(
        mutations, transactions, principals, new TenantId(properties.tenant()));
  }

  /** The session store of this process: nothing else holds a session (docs/identity.md). */
  @Bean
  InMemoryWebSessionStore webSessionStore() {
    return new InMemoryWebSessionStore();
  }

  /**
   * Replaces Boot's session manager so that this module holds the store it uses. The cookie is the
   * one Boot built from {@code server.reactive.session.cookie.*}.
   */
  @Bean(WebHttpHandlerBuilder.WEB_SESSION_MANAGER_BEAN_NAME)
  WebSessionManager webSessionManager(
      InMemoryWebSessionStore store, WebSessionIdResolver sessionIdResolver) {
    DefaultWebSessionManager manager = new DefaultWebSessionManager();
    manager.setSessionStore(store);
    manager.setSessionIdResolver(sessionIdResolver);
    return manager;
  }

  @Bean
  SessionRegistry sessionRegistry() {
    return new SessionRegistry();
  }

  @Bean
  ReactiveClientRegistrationRepository clientRegistrations(
      IdentityDiscovery discovery, SignInProperties properties) {
    return new DiscoveredClientRegistrations(discovery, properties);
  }

  /** The tokens of a session are kept in that session, in memory, and nowhere else. */
  @Bean
  ServerOAuth2AuthorizedClientRepository authorizedClientRepository() {
    return new WebSessionServerOAuth2AuthorizedClientRepository();
  }

  @Bean
  ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
      ReactiveClientRegistrationRepository registrations,
      ServerOAuth2AuthorizedClientRepository authorizedClients) {
    DefaultReactiveOAuth2AuthorizedClientManager manager =
        new DefaultReactiveOAuth2AuthorizedClientManager(registrations, authorizedClients);
    // Renewal only: a session is never re-authorized by sending the browser away from an API call.
    // A renewal replaces the tokens the session holds and nothing else. The framework's default
    // would also rebuild the session's principal from the renewed ID token, dropping the bound
    // principal; who the person is was decided at sign-in and does not change with a renewal, so
    // the renewed ID token is not used at all.
    manager.setAuthorizedClientProvider(
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .refreshToken(renewal ->
                renewal.authorizationSuccessHandler(
                    (authorizedClient, principal, attributes) -> Mono.empty()))
            .build());
    return manager;
  }

  @Bean
  SessionKeeper sessionKeeper(
      InMemoryWebSessionStore store,
      SessionRegistry registry,
      SessionLedger ledger,
      ReactiveOAuth2AuthorizedClientManager authorizedClientManager,
      ServerOAuth2AuthorizedClientRepository authorizedClients,
      IdentityDiscovery discovery,
      SignInProperties properties,
      Clock clock) {
    return new SessionKeeper(
        store,
        registry,
        ledger,
        authorizedClientManager,
        authorizedClients,
        discovery,
        properties,
        WebClient.create(),
        clock);
  }

  @Bean
  SignInResponses signInResponses(SignInProperties properties, ProblemResponses problems) {
    return new SignInResponses(properties, problems);
  }

  /** Verifies the identity provider's logout notices (issuer, this client as audience, expiry). */
  @Bean
  ReactiveJwtDecoder logoutTokenDecoder(
      IssuerSigningKeys keys, IdentityProperties identity, SignInProperties properties) {
    return CredentialValidation.decoder(
        keys, CredentialValidation.logoutToken(identity.issuerUri(), properties.clientId()));
  }

  @Bean
  SecurityWebFilterChain securityWebFilterChain(
      ServerHttpSecurity http,
      IssuerSigningKeys keys,
      IdentityProperties identity,
      SignInProperties properties,
      ReactiveClientRegistrationRepository registrations,
      ServerOAuth2AuthorizedClientRepository authorizedClients,
      SessionLedger ledger,
      SessionKeeper sessions,
      SignInResponses responses,
      InMemoryWebSessionStore store) {
    log.info(
        "Sign-in as client {} of {}; the application origin is {}",
        properties.clientId(),
        identity.issuerUri(),
        properties.applicationOrigin());
    // Kept in the session, not in a second cookie: the browser holds one cookie.
    ServerCsrfTokenRepository csrfTokens = new WebSessionServerCsrfTokenRepository();
    SignInOutcomeHandlers outcomes =
        new SignInOutcomeHandlers(sessions, ledger, responses, csrfTokens);
    ServerAuthenticationEntryPoint unauthenticated =
        (exchange, failure) -> responses.unauthorized(exchange);
    ServerAccessDeniedHandler denied = (exchange, failure) -> responses.forbidden(exchange);
    ServerWebExchangeMatcher publicContent =
        new OrServerWebExchangeMatcher(
            path(HttpMethod.GET, "/api/compatibility"),
            path(HttpMethod.GET, "/actuator/health"),
            path(HttpMethod.GET, "/actuator/health/**"));
    ServerWebExchangeMatcher signInSteps =
        new OrServerWebExchangeMatcher(
            path(HttpMethod.GET, SessionPaths.SESSION),
            path(HttpMethod.GET, SessionPaths.SIGN_IN),
            path(HttpMethod.GET, SessionPaths.CALLBACK),
            path(HttpMethod.POST, SessionPaths.BACKCHANNEL_LOGOUT));

    return http.authorizeExchange(exchanges ->
            exchanges
                .matchers(publicContent, signInSteps)
                .permitAll()
                .anyExchange()
                .authenticated())
        .oauth2Login(login ->
            login
                .clientRegistrationRepository(registrations)
                .authorizedClientRepository(authorizedClients)
                .authorizationRequestResolver(signInRequests(registrations, store))
                .authenticationMatcher(path(HttpMethod.GET, SessionPaths.CALLBACK))
                .authenticationManager(signInManager(ledger))
                .authenticationSuccessHandler(outcomes.success())
                .authenticationFailureHandler(outcomes.failure()))
        .oauth2ResourceServer(bearer ->
            bearer
                .jwt(jwt ->
                    jwt.jwtDecoder(
                            CredentialValidation.decoder(
                                keys,
                                CredentialValidation.bearer(
                                    identity.issuerUri(), properties.audience())))
                        .jwtAuthenticationConverter(bearerPrincipal(ledger)))
                .authenticationEntryPoint(unauthenticated)
                .accessDeniedHandler(denied)
                .authenticationFailureHandler(bearerRefused(ledger, responses)))
        .exceptionHandling(handling ->
            handling.authenticationEntryPoint(unauthenticated).accessDeniedHandler(denied))
        .csrf(csrf ->
            csrf.csrfTokenRepository(csrfTokens)
                .requireCsrfProtectionMatcher(
                    new AndServerWebExchangeMatcher(
                        CsrfWebFilter.DEFAULT_CSRF_MATCHER,
                        new NegatedServerWebExchangeMatcher(
                            new OrServerWebExchangeMatcher(
                                path(HttpMethod.POST, SessionPaths.BACKCHANNEL_LOGOUT),
                                SecurityConfiguration::bearerCall))))
                .accessDeniedHandler(denied))
        // No page of this backend exists to return to, and an API call is never sent to a login.
        .requestCache(cache -> cache.requestCache(NoOpServerRequestCache.getInstance()))
        .logout(ServerHttpSecurity.LogoutSpec::disable)
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .addFilterAfter(outcomes.providerOutage(), SecurityWebFiltersOrder.HTTP_HEADERS_WRITER)
        .addFilterAfter(
            SessionWebFilters.standing(
                sessions,
                responses,
                publicContent,
                path(HttpMethod.POST, SessionPaths.SIGN_OUT),
                path(HttpMethod.GET, SessionPaths.SESSION)),
            SecurityWebFiltersOrder.LOGOUT)
        .addFilterAfter(
            SessionWebFilters.scope(ledger.tenant()), SecurityWebFiltersOrder.AUTHORIZATION)
        .build();
  }

  private static ServerWebExchangeMatcher path(HttpMethod method, String pattern) {
    return new PathPatternParserServerWebExchangeMatcher(pattern, method);
  }

  private static Mono<MatchResult> bearerCall(ServerWebExchange exchange) {
    return presentsBearer(exchange) ? MatchResult.match() : MatchResult.notMatch();
  }

  private static boolean presentsBearer(ServerWebExchange exchange) {
    String authorization = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
    return authorization != null
        && authorization.regionMatches(true, 0, BEARER_PREFIX, 0, BEARER_PREFIX.length());
  }

  /**
   * Sign-in starts only at {@link SessionPaths#SIGN_IN}. The state of an unfinished sign-in is kept
   * for a short time, so abandoned attempts do not fill the session store.
   */
  private static ServerOAuth2AuthorizationRequestResolver signInRequests(
      ReactiveClientRegistrationRepository registrations, InMemoryWebSessionStore store) {
    DefaultServerOAuth2AuthorizationRequestResolver delegate =
        new DefaultServerOAuth2AuthorizationRequestResolver(registrations);
    ServerWebExchangeMatcher signIn = path(HttpMethod.GET, SessionPaths.SIGN_IN);
    return new ServerOAuth2AuthorizationRequestResolver() {
      @Override
      public Mono<OAuth2AuthorizationRequest> resolve(ServerWebExchange exchange) {
        // A browser that already has a session starts no second sign-in: the request goes on to
        // SessionController, which sends it back to the shell. To change the person, sign out.
        return signIn
            .matches(exchange)
            .filter(MatchResult::isMatch)
            .filterWhen(match ->
                ReactiveSecurityContextHolder.getContext()
                    .map(context -> SessionWebFilters.principalOf(context.getAuthentication()))
                    .map(Optional::isEmpty)
                    .defaultIfEmpty(true))
            // A full store would fail when the new session is saved, as a 500 without a cause.
            .flatMap(match ->
                full(store)
                    ? Mono.error(new SessionCapacityExceededException())
                    : resolve(exchange, DiscoveredClientRegistrations.REGISTRATION_ID));
      }

      @Override
      public Mono<OAuth2AuthorizationRequest> resolve(
          ServerWebExchange exchange, String clientRegistrationId) {
        return delegate
            .resolve(exchange, clientRegistrationId)
            .delayUntil(request ->
                exchange
                    .getSession()
                    .doOnNext(session -> session.setMaxIdleTime(SessionKeeper.PENDING_SIGN_IN)));
      }
    };
  }

  /** Whether the store has no room for one more session, after dropping the expired ones. */
  private static boolean full(InMemoryWebSessionStore store) {
    if (store.getSessions().size() < store.getMaxSessions()) {
      return false;
    }
    store.removeExpiredSessions();
    return store.getSessions().size() >= store.getMaxSessions();
  }

  /**
   * Completes a sign-in: exchanges the code, validates the ID token (signature, issuer, audience,
   * expiry, nonce) and binds the person. Anything that is not a refusal of the credential (the
   * provider unreachable, the principal store failing) is reported as a service failure, so the
   * outcome handler tells an outage from a refusal.
   */
  private static ReactiveAuthenticationManager signInManager(SessionLedger ledger) {
    return signInManager(ledger, CredentialValidation.PROVIDER_TIMEOUT, Schedulers.parallel());
  }

  /**
   * The two steps the identity provider does are bounded, each by {@code providerTimeout} on {@code
   * timer}: the code exchange, and the decoding of the ID token, which fetches the issuer's keys. A
   * provider that never answers ends the sign-in as an outage instead of holding the request.
   * Binding the person and recording the sign-in ({@link PersonUserService}) is this backend's own
   * work and is not bounded here: a record that commits late is still the record of a sign-in that
   * completed, and cutting it off would leave a recorded sign-in without a session.
   *
   * <p>The ID token's decoder is the framework's, and one is kept and used for every sign-in of the
   * same registration (issuer, client, key endpoint): it holds the issuer's keys, so the keys are
   * fetched when a sign-in first needs them and again only when an ID token names a key the decoder
   * does not hold. A decoder made per sign-in would fetch them every time. The ID token arrives on
   * the backend's own connection to the token endpoint and is not something a caller can present,
   * so this key source has no bound on its fetches and no maximum age, unlike {@link
   * IssuerSigningKeys}.
   */
  static ReactiveAuthenticationManager signInManager(
      SessionLedger ledger, Duration providerTimeout, Scheduler timer) {
    WebClientReactiveAuthorizationCodeTokenResponseClient codeExchange =
        new WebClientReactiveAuthorizationCodeTokenResponseClient();
    ReactiveOidcIdTokenDecoderFactory idTokenDecoders = new ReactiveOidcIdTokenDecoderFactory();
    OidcAuthorizationCodeReactiveAuthenticationManager oidc =
        new OidcAuthorizationCodeReactiveAuthenticationManager(
            grant ->
                CredentialValidation.withinProviderTimeout(
                    Mono.defer(() -> codeExchange.getTokenResponse(grant)), providerTimeout, timer),
            new PersonUserService(ledger));
    AtomicReference<IdTokenDecoder> kept = new AtomicReference<>();
    oidc.setJwtDecoderFactory(registration -> {
      ReactiveJwtDecoder decoder =
          kept.updateAndGet(current ->
                  current != null && current.serves(registration)
                      ? current
                      : IdTokenDecoder.of(
                          registration, idTokenDecoders.createDecoder(registration)))
              .decoder();
      return idToken ->
          CredentialValidation.withinProviderTimeout(
              Mono.defer(() -> decoder.decode(idToken)), providerTimeout, timer);
    });
    return authentication ->
        oidc.authenticate(authentication)
            .switchIfEmpty(
                Mono.error(
                    () -> new OAuth2AuthenticationException(new OAuth2Error("invalid_id_token"))))
            // Keys that could not be fetched say nothing about the ID token: an outage too.
            .onErrorMap(
                failure ->
                    !(failure instanceof AuthenticationException)
                        || CredentialValidation.couldNotVerify(failure),
                failure ->
                    new AuthenticationServiceException("sign-in could not be completed", failure));
  }

  /**
   * The ID-token decoder of one registration, named by what the decoder was built from: the issuer
   * and the client it checks the token against, and the address it fetches the keys from. The
   * registration itself is built anew from the discovery document for every sign-in.
   */
  private record IdTokenDecoder(
      String issuer, String clientId, String keyEndpoint, ReactiveJwtDecoder decoder) {

    static IdTokenDecoder of(ClientRegistration registration, ReactiveJwtDecoder decoder) {
      return new IdTokenDecoder(
          registration.getProviderDetails().getIssuerUri(),
          registration.getClientId(),
          registration.getProviderDetails().getJwkSetUri(),
          decoder);
    }

    boolean serves(ClientRegistration registration) {
      return Objects.equals(issuer, registration.getProviderDetails().getIssuerUri())
          && Objects.equals(clientId, registration.getClientId())
          && Objects.equals(keyEndpoint, registration.getProviderDetails().getJwkSetUri());
    }
  }

  /**
   * Binds a validated bearer credential to its principal by issuer and subject. Both failures end
   * in {@link #bearerRefused}: an unusable identity as a recorded refusal (401), a failing store as
   * an outage (503).
   */
  private static Converter<Jwt, Mono<AbstractAuthenticationToken>> bearerPrincipal(
      SessionLedger ledger) {
    return credential -> {
      ExternalIdentity identity;
      try {
        identity =
            new ExternalIdentity(credential.getClaimAsString("iss"), credential.getSubject());
      } catch (IllegalArgumentException unusable) {
        // Validly signed, but its issuer or subject is not one a principal can be bound to.
        return Mono.error(
            new InvalidBearerTokenException("the credential names no usable subject"));
      }
      return ledger
          .principalOf(identity)
          .<AbstractAuthenticationToken>map(
              principal -> new SessionWebFilters.BoundBearerAuthentication(credential, principal))
          // The principal store failing is an outage (503), not a judgement on the credential.
          .onErrorMap(
              failure -> !(failure instanceof AuthenticationException),
              failure ->
                  new AuthenticationServiceException("the principal could not be bound", failure));
    };
  }

  /**
   * A bearer credential that was refused: recorded under its fixed reason code and answered 401
   * with the challenge and no description. A failure to verify at all (keys or principal store
   * unavailable) is 503.
   */
  private static ServerAuthenticationFailureHandler bearerRefused(
      SessionLedger ledger, SignInResponses responses) {
    return (webFilterExchange, failure) -> {
      ServerWebExchange exchange = webFilterExchange.getExchange();
      // The filter that calls this also sees every authentication failure raised further down
      // the chain; only a failure of a presented bearer credential is this handler's.
      if (!presentsBearer(exchange)) {
        return Mono.error(failure);
      }
      if (failure instanceof AuthenticationServiceException) {
        log.warn(
            "{}Bearer credential could not be verified: {}",
            exchange.getLogPrefix(),
            SafeFailure.describe(failure));
        return responses.outage(exchange);
      }
      return ledger
          .credentialRefused(CredentialValidation.reasonOf(failure), exchange.getRequest().getId())
          .then(
              Mono.defer(() ->
                  responses.unauthorized(
                      exchange, SignInResponses.CHALLENGE + " error=\"invalid_token\"")));
    };
  }
}
