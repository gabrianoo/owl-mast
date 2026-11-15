package com.aisquad.owlmast.access.adapter.web;

import static org.mockito.Mockito.mock;

import com.aisquad.owlmast.access.adapter.identity.IdentityDiscovery;
import com.aisquad.owlmast.access.adapter.identity.IdentityProperties;
import com.aisquad.owlmast.access.adapter.identity.SignInProperties;
import com.aisquad.owlmast.access.application.SessionLedger;
import com.aisquad.owlmast.access.port.PrincipalStore;
import com.aisquad.owlmast.audit.api.AuditedMutation;
import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.audit.api.AuditedResult;
import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.platform.scope.TenantId;
import com.aisquad.owlmast.platform.web.ProblemResponses;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.web.server.WebSessionServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.WebSession;
import org.springframework.web.server.session.InMemoryWebSessionStore;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

/**
 * The session machinery of this package wired for a unit test: the real store, registry, keeper,
 * ledger and handlers; a clock the test moves; an identity provider whose renewal answer and logout
 * status the test chooses (a local server publishes its discovery document); and an audit owner
 * that records what would have been written instead of writing it.
 */
final class SessionFixture implements AutoCloseable {

  static final String ISSUER_PATH = "/realms/owl-mast";
  static final Duration CALL = Duration.ofSeconds(10);

  /** One recorded outcome: what {@code AuditedMutations} was asked to record and how it ended. */
  record Outcome(String action, String outcome, String actorId, String reason) {}

  final MutableClock clock = new MutableClock(Instant.parse("2026-11-15T10:00:00Z"));
  final InMemoryWebSessionStore store = new InMemoryWebSessionStore();
  final SessionRegistry registry = new SessionRegistry();
  final List<Outcome> outcomes = new CopyOnWriteArrayList<>();
  final AtomicReference<Supplier<Mono<OAuth2AuthorizedClient>>> renewal =
      new AtomicReference<>(Mono::empty);
  final AtomicInteger logoutStatus = new AtomicInteger(204);
  final AtomicInteger logoutCalls = new AtomicInteger();
  final WebSessionServerOAuth2AuthorizedClientRepository authorizedClients =
      new WebSessionServerOAuth2AuthorizedClientRepository();
  final SignInProperties properties =
      new SignInProperties("owl-mast-web", "synthetic", "https://owl.example", null, "default");
  final SessionLedger ledger;
  final SessionKeeper keeper;
  final SignInResponses responses;
  private final DisposableServer provider;
  private final String issuer;

  SessionFixture() {
    store.setClock(clock);
    provider =
        HttpServer.create()
            .port(0)
            .route(routes ->
                routes
                    .get(
                        ISSUER_PATH + "/.well-known/openid-configuration",
                        (request, response) ->
                            response
                                .header("Content-Type", "application/json")
                                .sendString(Mono.fromSupplier(this::document)))
                    .post(
                        ISSUER_PATH + "/protocol/openid-connect/logout",
                        (request, response) -> {
                          logoutCalls.incrementAndGet();
                          return response.status(logoutStatus.get()).send();
                        }))
            .bindNow();
    issuer = "http://localhost:" + provider.port() + ISSUER_PATH;
    AuditedMutations recording =
        new AuditedMutations() {
          @Override
          public <T> Mono<AuditedResult<T>> execute(AuditedMutation<T> mutation) {
            String actor = mutation.actor().id().orElse(null);
            return Scopes.current()
                .flatMap(scope -> mutation.business().apply(scope))
                .map(done -> {
                  outcomes.add(new Outcome(mutation.action(), "SUCCEEDED", actor, null));
                  return new AuditedResult<>(done.value(), UUID.randomUUID());
                })
                .doOnError(failure ->
                    outcomes.add(
                        failure instanceof OperationDeniedException denied
                            ? new Outcome(mutation.action(), "DENIED", actor, denied.reasonCode())
                            : new Outcome(
                                mutation.action(),
                                "FAILED",
                                actor,
                                failure.getClass().getSimpleName())));
          }
        };
    ledger =
        new SessionLedger(
            recording,
            new ScopedTransactions(mock(TransactionalOperator.class), mock(DatabaseClient.class)),
            mock(PrincipalStore.class),
            new TenantId("default"));
    ReactiveOAuth2AuthorizedClientManager manager = request -> renewal.get().get();
    keeper =
        new SessionKeeper(
            store,
            registry,
            ledger,
            manager,
            authorizedClients,
            new IdentityDiscovery(WebClient.create(), new IdentityProperties(issuer, true)),
            properties,
            WebClient.create(),
            clock);
    responses =
        new SignInResponses(properties, new ProblemResponses(ServerCodecConfigurer.create()));
  }

  /** The provider answers a renewal with this OAuth error code. */
  void renewalFailsWith(String errorCode) {
    renewal.set(() -> Mono.error(new OAuth2AuthorizationException(new OAuth2Error(errorCode))));
  }

  /** The provider renews: the session's tokens are good for another five minutes. */
  void renewalSucceeds() {
    renewal.set(() -> Mono.just(client("renewed", true)));
  }

  /** A started session held by the store, as a completed request leaves it. */
  WebSession session() {
    WebSession session = store.createWebSession().block(CALL);
    session.start();
    session.save().block(CALL);
    return session;
  }

  MockServerWebExchange exchange(MockServerHttpRequest.BaseBuilder<?> request, WebSession session) {
    return MockServerWebExchange.builder(request.build())
        .sessionManager(exchange -> Mono.just(session))
        .build();
  }

  SignedInPerson person(String sessionRef, String subject) {
    Map<String, Object> claims =
        Map.of("iss", issuer, "sub", subject, "sid", "sid-" + sessionRef, "name", "Ada Synthetic");
    return new SignedInPerson(
        new OidcIdToken("synthetic", clock.instant(), clock.instant().plusSeconds(300), claims),
        new PrincipalId("person:" + subject),
        sessionRef);
  }

  static OAuth2AuthenticationToken authentication(SignedInPerson person) {
    return new OAuth2AuthenticationToken(
        person, List.of(), DiscoveredClientRegistrations.REGISTRATION_ID);
  }

  OAuth2AuthorizedClient client(String name, boolean withRefreshToken) {
    ClientRegistration registration =
        ClientRegistration.withRegistrationId(DiscoveredClientRegistrations.REGISTRATION_ID)
            .clientId("owl-mast-web")
            .clientSecret("synthetic")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("https://owl.example/api/session/callback")
            .authorizationUri(issuer + "/auth")
            .tokenUri(issuer + "/protocol/openid-connect/token")
            .build();
    return new OAuth2AuthorizedClient(
        registration,
        name,
        new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "synthetic-access",
            clock.instant(),
            clock.instant().plusSeconds(300)),
        withRefreshToken ? new OAuth2RefreshToken("synthetic-refresh", clock.instant()) : null);
  }

  List<String> actions() {
    return outcomes.stream().map(Outcome::action).toList();
  }

  @Override
  public void close() {
    provider.disposeNow();
  }

  private String document() {
    return "{\"issuer\":\""
        + issuer
        + "\",\"authorization_endpoint\":\""
        + issuer
        + "/auth\",\"token_endpoint\":\""
        + issuer
        + "/protocol/openid-connect/token\",\"jwks_uri\":\""
        + issuer
        + "/certs\"}";
  }

  /** A clock that stands still until the test moves it. */
  static final class MutableClock extends Clock {

    private final AtomicReference<Instant> now;

    MutableClock(Instant start) {
      this.now = new AtomicReference<>(start);
    }

    void advance(Duration by) {
      now.updateAndGet(current -> current.plus(by));
    }

    @Override
    public Instant instant() {
      return now.get();
    }

    @Override
    public ZoneId getZone() {
      return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return this;
    }
  }
}
