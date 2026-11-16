package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.RETURNS_DEEP_STUBS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.aisquad.owlmast.access.adapter.identity.SigningIssuer;
import com.aisquad.owlmast.access.adapter.identity.SigningIssuer.Answer;
import com.aisquad.owlmast.access.adapter.web.SessionFixture.Outcome;
import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import com.aisquad.owlmast.access.application.SessionLedger;
import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.access.port.PrincipalStore;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.TenantId;
import com.nimbusds.jwt.JWTClaimsSet;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import java.util.function.IntSupplier;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthorizationCodeAuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationExchange;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationResponse;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.reactive.AbstractReactiveTransactionManager;
import org.springframework.transaction.reactive.GenericReactiveTransaction;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;
import reactor.test.scheduler.VirtualTimeScheduler;

/**
 * What the time given to the identity provider bounds at the end of a sign-in (PR #194 review,
 * R1-5): the code exchange and the ID token's keys, each on its own, and not the record of the
 * sign-in. The provider is a local issuer whose endpoints answer as a test says; the principal
 * store and the audit owner are stand-ins; the time runs on a clock the test moves, so no assertion
 * depends on how fast this machine is.
 */
class SignInManagerTest {

  /** Real-time bound for one answer of the local issuer; never part of a timing assertion. */
  private static final Duration ANSWER = Duration.ofSeconds(30);

  private static final String CLIENT = "owl-mast-web";
  private static final String REDIRECT = "https://owl.example/api/session/callback";
  private static final String NONCE = "synthetic-nonce";
  private static final PrincipalId ADA = new PrincipalId("person:ada");

  private final SigningIssuer issuer = new SigningIssuer();
  private final VirtualTimeScheduler time = VirtualTimeScheduler.create();
  private final List<Outcome> outcomes = new CopyOnWriteArrayList<>();
  private final CountDownLatch recording = new CountDownLatch(1);

  /** How long the principal store takes to record the sign-in, on the test's clock. */
  private final AtomicReference<Duration> recordTakes = new AtomicReference<>(Duration.ZERO);

  private final ReactiveAuthenticationManager manager =
      SecurityConfiguration.signInManager(ledger(), CredentialValidation.PROVIDER_TIMEOUT, time);

  @AfterEach
  void stop() {
    issuer.close();
  }

  @Test
  void aSignInTheProviderAnswersBindsThePersonAndIsRecordedOnce() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));

    Authentication signedIn = manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS);

    assertThat(signedIn.getPrincipal()).isInstanceOf(SignedInPerson.class);
    assertThat(((SignedInPerson) signedIn.getPrincipal()).principalId()).isEqualTo(ADA);
    assertThat(outcomes)
        .containsExactly(new Outcome("session.sign-in", "SUCCEEDED", ADA.value(), null));
    assertThat(issuer.tokenRequests()).isEqualTo(1);
  }

  /**
   * R2-4: the ID token's keys are fetched when a sign-in first needs them, not at every sign-in.
   * Each callback arrives with a registration built anew, as in production. Before, a decoder was
   * made per sign-in and each fetched the keys.
   */
  @Test
  void theIdTokenKeysAreFetchedOnceForSignInsOfTheSameRegistration() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));

    for (int signIn = 0; signIn < 3; signIn++) {
      assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();
    }

    assertThat(issuer.tokenRequests()).isEqualTo(3);
    assertThat(issuer.keyRequests()).isEqualTo(1);
  }

  /**
   * The kept decoder belongs to one registration. When the discovery document names another issuer
   * and key endpoint, the next sign-in gets a decoder of its own: the keys come from the new
   * endpoint, and a token only the new issuer signed is accepted.
   */
  @Test
  void aRegistrationThatNamesAnotherIssuerAndKeyEndpointGetsItsOwnDecoder() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();

    try (SigningIssuer other = new SigningIssuer()) {
      other.tokenAnswer(tokenAnswer(other, idToken -> {}));
      Authentication signedIn =
          manager.authenticate(callback(other)).toFuture().get(30, TimeUnit.SECONDS);

      assertThat(signedIn.getPrincipal()).isInstanceOf(SignedInPerson.class);
      assertThat(other.keyRequests()).isEqualTo(1);
      assertThat(issuer.keyRequests()).isEqualTo(1);
    }
  }

  /**
   * R3-2: the key endpoint alone names another decoder. The discovery document moves the key
   * endpoint and nothing else; the next sign-in fetches from the new endpoint, so a token signed
   * with a key only that endpoint publishes is accepted, and the earlier endpoint is not asked
   * again.
   */
  @Test
  void aRegistrationThatNamesOnlyAnotherKeyEndpointFetchesItsKeysThere() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();

    try (SigningIssuer moved = new SigningIssuer()) {
      // The same issuer and token endpoint; the ID token names the issuer and is signed with the
      // key the new endpoint publishes.
      issuer.tokenAnswer(idTokenAnswer(moved.sign(idTokenClaims(idToken -> {}))));
      Authentication signedIn =
          manager
              .authenticate(
                  callback(CLIENT, issuer.issuerUri(), issuer.tokenEndpoint(), moved.keyEndpoint()))
              .toFuture()
              .get(30, TimeUnit.SECONDS);

      assertThat(signedIn.getPrincipal()).isInstanceOf(SignedInPerson.class);
      assertThat(moved.keyRequests()).isEqualTo(1);
      assertThat(issuer.keyRequests()).isEqualTo(1);
    }
  }

  /**
   * R3-2: the issuer alone names another decoder. The token and key endpoints stay; a token that
   * names the new issuer is accepted, which the kept decoder, checking the earlier issuer, would
   * refuse. The new decoder fetches the keys for itself.
   */
  @Test
  void aRegistrationThatNamesOnlyAnotherIssuerGetsADecoderThatChecksThatIssuer() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();

    String renamed = issuer.issuerUri() + "-renamed";
    issuer.tokenAnswer(tokenAnswer(idToken -> idToken.issuer(renamed)));
    Authentication signedIn =
        manager
            .authenticate(callback(CLIENT, renamed, issuer.tokenEndpoint(), issuer.keyEndpoint()))
            .toFuture()
            .get(30, TimeUnit.SECONDS);

    assertThat(signedIn.getPrincipal()).isInstanceOf(SignedInPerson.class);
    assertThat(issuer.keyRequests()).isEqualTo(2);

    // The new decoder checks the new issuer only: a token naming the earlier one is now refused.
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThatThrownBy(() ->
            manager
                .authenticate(
                    callback(CLIENT, renamed, issuer.tokenEndpoint(), issuer.keyEndpoint()))
                .block(ANSWER))
        .isInstanceOf(OAuth2AuthenticationException.class)
        .matches(failure -> !CredentialValidation.couldNotVerify(failure));
  }

  /**
   * R3-2: the client alone names another decoder. A token for the new client is accepted, which the
   * kept decoder, checking the earlier client as the audience, would refuse.
   */
  @Test
  void aRegistrationThatNamesOnlyAnotherClientGetsADecoderThatChecksThatClient() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();

    String client = "owl-mast-web-2";
    issuer.tokenAnswer(tokenAnswer(idToken -> idToken.audience(client)));
    Authentication signedIn =
        manager
            .authenticate(
                callback(client, issuer.issuerUri(), issuer.tokenEndpoint(), issuer.keyEndpoint()))
            .toFuture()
            .get(30, TimeUnit.SECONDS);

    assertThat(signedIn.getPrincipal()).isInstanceOf(SignedInPerson.class);
    assertThat(issuer.keyRequests()).isEqualTo(2);

    // The new decoder checks the new client only: a token for the earlier one is now refused.
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThatThrownBy(() ->
            manager
                .authenticate(
                    callback(
                        client, issuer.issuerUri(), issuer.tokenEndpoint(), issuer.keyEndpoint()))
                .block(ANSWER))
        .isInstanceOf(OAuth2AuthenticationException.class)
        .matches(failure -> !CredentialValidation.couldNotVerify(failure));
  }

  /**
   * R3-2: the token endpoint is not part of the decoder's name. A document that moves only the
   * token endpoint keeps the decoder: the code is exchanged at the new endpoint and no key is
   * fetched again.
   */
  @Test
  void aRegistrationThatNamesOnlyAnotherTokenEndpointKeepsTheDecoder() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();

    try (SigningIssuer moved = new SigningIssuer()) {
      moved.tokenAnswer(tokenAnswer(idToken -> {}));
      Authentication signedIn =
          manager
              .authenticate(
                  callback(CLIENT, issuer.issuerUri(), moved.tokenEndpoint(), issuer.keyEndpoint()))
              .toFuture()
              .get(30, TimeUnit.SECONDS);

      assertThat(signedIn.getPrincipal()).isInstanceOf(SignedInPerson.class);
      assertThat(moved.tokenRequests()).isEqualTo(1);
      assertThat(issuer.tokenRequests()).isEqualTo(1);
      assertThat(issuer.keyRequests()).isEqualTo(1);
      assertThat(moved.keyRequests()).isZero();
    }
  }

  /** A key the issuer starts signing ID tokens with is fetched when a token names it. */
  @Test
  void anIdTokenNamingAKeyTheDecoderDoesNotHoldCausesAFetch() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();

    issuer.rotateTo("key-2");
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    assertThat(manager.authenticate(callback()).toFuture().get(30, TimeUnit.SECONDS)).isNotNull();

    assertThat(issuer.keyRequests()).isEqualTo(2);
  }

  /**
   * R1-5: the record of the sign-in commits later than the time given to the provider. The sign-in
   * completes and is recorded once; before, the bound around the whole step cut it off, leaving a
   * recorded sign-in without a session and a second, FAILED record of the same sign-in.
   */
  @Test
  void aSignInRecordThatCommitsAfterTheProviderTimeStillCompletesTheSignIn() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    recordTakes.set(CredentialValidation.PROVIDER_TIMEOUT.plusSeconds(5));

    CompletableFuture<Authentication> signIn = manager.authenticate(callback()).toFuture();
    // The provider has done its part: the code was exchanged and the ID token verified.
    assertThat(recording.await(ANSWER.toSeconds(), TimeUnit.SECONDS)).isTrue();

    time.advanceTimeBy(CredentialValidation.PROVIDER_TIMEOUT.plusSeconds(1));
    assertThat(signIn).isNotDone();
    assertThat(outcomes).isEmpty();
    time.advanceTimeBy(Duration.ofSeconds(4));

    Authentication signedIn = signIn.get(ANSWER.toSeconds(), TimeUnit.SECONDS);
    assertThat(signedIn.getPrincipal()).isInstanceOf(SignedInPerson.class);
    assertThat(outcomes)
        .containsExactly(new Outcome("session.sign-in", "SUCCEEDED", ADA.value(), null));
  }

  @Test
  void aTokenEndpointThatNeverAnswersIsAnOutageWhenItsTimeHasPassed() throws Exception {
    issuer.tokensAre(Answer.UNANSWERED);

    CompletableFuture<Authentication> signIn = manager.authenticate(callback()).toFuture();
    await(issuer::tokenRequests);
    time.advanceTimeBy(CredentialValidation.PROVIDER_TIMEOUT.minusMillis(1));
    assertThat(signIn).isNotDone();
    time.advanceTimeBy(Duration.ofMillis(1));

    assertOutage(signIn);
    assertThat(issuer.keyRequests()).isZero();
  }

  @Test
  void aKeyEndpointThatNeverAnswersIsAnOutageWhenItsTimeHasPassed() throws Exception {
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    issuer.keysAre(Answer.UNANSWERED);

    CompletableFuture<Authentication> signIn = manager.authenticate(callback()).toFuture();
    await(issuer::keyRequests);
    time.advanceTimeBy(CredentialValidation.PROVIDER_TIMEOUT.minusMillis(1));
    assertThat(signIn).isNotDone();
    time.advanceTimeBy(Duration.ofMillis(1));

    assertOutage(signIn);
  }

  /**
   * Endpoints that fail at once. The token endpoint's 5xx arrives as the framework's {@code
   * invalid_token_response}, which the outcome handler reads as an outage ({@code
   * SignInOutcomeHandlersTest}); keys that cannot be fetched are a service failure here.
   */
  @Test
  void endpointsThatFailAtOnceAreAnOutageToo() {
    issuer.tokensAre(Answer.FAILING);
    assertThatThrownBy(() -> manager.authenticate(callback()).block(ANSWER))
        .isInstanceOfSatisfying(
            OAuth2AuthenticationException.class,
            failure ->
                assertThat(failure.getError().getErrorCode()).isEqualTo("invalid_token_response"));

    issuer.tokensAre(Answer.SERVED);
    issuer.tokenAnswer(tokenAnswer(idToken -> {}));
    issuer.keysAre(Answer.FAILING);
    assertThatThrownBy(() -> manager.authenticate(callback()).block(ANSWER))
        .isInstanceOf(AuthenticationServiceException.class);
    assertThat(outcomes).isEmpty();
  }

  /** A refusal stays a refusal: the bound around the provider's steps does not turn it into one. */
  @Test
  void anIdTokenTheIssuerDidNotSignIsRefusedNotAnOutage() {
    issuer.tokenAnswer(
        "{\"access_token\":\"synthetic-access\",\"token_type\":\"Bearer\",\"expires_in\":300,"
            + "\"id_token\":\""
            + issuer.forged(idTokenClaims(idToken -> {}))
            + "\"}");

    assertThatThrownBy(() -> manager.authenticate(callback()).block(ANSWER))
        .isInstanceOf(OAuth2AuthenticationException.class)
        .matches(failure -> !CredentialValidation.couldNotVerify(failure));
    assertThat(outcomes).isEmpty();
  }

  private void assertOutage(CompletableFuture<Authentication> signIn) {
    assertThatThrownBy(() -> signIn.get(ANSWER.toSeconds(), TimeUnit.SECONDS))
        .cause()
        .isInstanceOf(AuthenticationServiceException.class)
        .hasCauseInstanceOf(IdentityProviderUnavailableException.class);
    assertThat(outcomes).isEmpty();
  }

  /** Waits (real time, bounded) until the issuer has received one request of that kind. */
  private static void await(IntSupplier requests) throws InterruptedException {
    long deadline = System.nanoTime() + ANSWER.toNanos();
    while (requests.getAsInt() < 1 && System.nanoTime() < deadline) {
      Thread.sleep(5);
    }
    assertThat(requests.getAsInt()).isEqualTo(1);
  }

  /** The browser's return from the identity provider with a code for a sign-in it started. */
  private OAuth2AuthorizationCodeAuthenticationToken callback() {
    return callback(issuer);
  }

  /** The same return, with the registration a discovery document of {@code provider} gives. */
  private static OAuth2AuthorizationCodeAuthenticationToken callback(SigningIssuer provider) {
    return callback(CLIENT, provider.issuerUri(), provider.tokenEndpoint(), provider.keyEndpoint());
  }

  /** The same return, with a registration that names exactly these four values. */
  private static OAuth2AuthorizationCodeAuthenticationToken callback(
      String client, String issuerUri, String tokenEndpoint, String keyEndpoint) {
    ClientRegistration registration =
        ClientRegistration.withRegistrationId(DiscoveredClientRegistrations.REGISTRATION_ID)
            .clientId(client)
            .clientSecret("synthetic")
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(REDIRECT)
            .scope("openid")
            .authorizationUri(issuerUri + "/auth")
            .tokenUri(tokenEndpoint)
            .jwkSetUri(keyEndpoint)
            .issuerUri(issuerUri)
            .userNameAttributeName("sub")
            .build();
    OAuth2AuthorizationRequest request =
        OAuth2AuthorizationRequest.authorizationCode()
            .clientId(client)
            .authorizationUri(issuerUri + "/auth")
            .redirectUri(REDIRECT)
            .scope("openid")
            .state("synthetic-state")
            .attributes(Map.of("nonce", NONCE))
            .build();
    OAuth2AuthorizationResponse response =
        OAuth2AuthorizationResponse.success("synthetic-code")
            .redirectUri(REDIRECT)
            .state("synthetic-state")
            .build();
    return new OAuth2AuthorizationCodeAuthenticationToken(
        registration, new OAuth2AuthorizationExchange(request, response));
  }

  /** The token endpoint's answer with an ID token the issuer signed. */
  private String tokenAnswer(Consumer<JWTClaimsSet.Builder> change) {
    return tokenAnswer(issuer, change);
  }

  private static String tokenAnswer(SigningIssuer provider, Consumer<JWTClaimsSet.Builder> change) {
    return idTokenAnswer(provider.sign(idTokenClaims(provider, change)));
  }

  /** The token endpoint's answer that carries this signed ID token. */
  private static String idTokenAnswer(String idToken) {
    return "{\"access_token\":\"synthetic-access\",\"token_type\":\"Bearer\",\"expires_in\":300,"
        + "\"refresh_token\":\"synthetic-refresh\",\"id_token\":\""
        + idToken
        + "\"}";
  }

  private Consumer<JWTClaimsSet.Builder> idTokenClaims(Consumer<JWTClaimsSet.Builder> change) {
    return idTokenClaims(issuer, change);
  }

  private static Consumer<JWTClaimsSet.Builder> idTokenClaims(
      SigningIssuer provider, Consumer<JWTClaimsSet.Builder> change) {
    return provider
        .claims(CLIENT, "ada")
        .andThen(claims -> claims.claim("nonce", hashed(NONCE)).claim("name", "Ada Synthetic"))
        .andThen(change);
  }

  /** The ID token carries the SHA-256 of the nonce the sign-in was started with. */
  private static String hashed(String nonce) {
    try {
      return Base64.getUrlEncoder()
          .withoutPadding()
          .encodeToString(
              MessageDigest.getInstance("SHA-256")
                  .digest(nonce.getBytes(StandardCharsets.US_ASCII)));
    } catch (NoSuchAlgorithmException failure) {
      throw new IllegalStateException(failure);
    }
  }

  /**
   * The real ledger over a principal store that binds everybody to one principal and takes {@link
   * #recordTakes} to record a sign-in, a transaction that needs no database and an audit owner that
   * notes what it would have written.
   */
  private SessionLedger ledger() {
    PrincipalStore principals =
        new PrincipalStore() {
          @Override
          public Mono<PrincipalId> bind(ExternalIdentity identity) {
            return Mono.just(ADA);
          }

          @Override
          public Mono<Long> recordSignIn(PrincipalId principal) {
            // The completion is on the test's clock before the test is told: the test moves the
            // clock only after the latch, so it cannot move it past a completion not yet scheduled.
            return Mono.create(sink -> {
              time.schedule(
                  () -> sink.success(1L), recordTakes.get().toMillis(), TimeUnit.MILLISECONDS);
              recording.countDown();
            });
          }
        };
    DatabaseClient database = mock(DatabaseClient.class, RETURNS_DEEP_STUBS);
    when(database.sql(anyString()).bind(anyString(), any()).bind(anyString(), any()).then())
        .thenReturn(Mono.empty());
    return new SessionLedger(
        SessionFixture.recording(outcomes),
        new ScopedTransactions(TransactionalOperator.create(new NoDatabase()), database),
        principals,
        new TenantId("default"));
  }

  /** A transaction manager whose transactions begin, commit and roll back without a database. */
  private static final class NoDatabase extends AbstractReactiveTransactionManager {

    @Override
    protected Object doGetTransaction(TransactionSynchronizationManager synchronizations) {
      return new Object();
    }

    @Override
    protected Mono<Void> doBegin(
        TransactionSynchronizationManager synchronizations,
        Object transaction,
        TransactionDefinition definition) {
      return Mono.empty();
    }

    @Override
    protected Mono<Void> doCommit(
        TransactionSynchronizationManager synchronizations, GenericReactiveTransaction status) {
      return Mono.empty();
    }

    @Override
    protected Mono<Void> doRollback(
        TransactionSynchronizationManager synchronizations, GenericReactiveTransaction status) {
      return Mono.empty();
    }
  }
}
