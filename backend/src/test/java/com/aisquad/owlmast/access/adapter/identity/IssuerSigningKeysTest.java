package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.access.adapter.identity.SigningIssuer.Answer;
import com.aisquad.owlmast.access.application.IdentityProviderUnavailableException;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.testing.StubIdentityProvider;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jwt.SignedJWT;
import java.text.ParseException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.scheduler.VirtualTimeScheduler;

/**
 * How often the issuer is asked for its keys, whatever the presented tokens name, and how long a
 * held key is served without asking (PR #194 review, R1-1, R1-3 and R2-2). The intervals run on a
 * clock the test moves; the key endpoint is a local server that counts its requests.
 */
@ExtendWith(OutputCaptureExtension.class)
class IssuerSigningKeysTest {

  /** Real-time bound for one answer of the local issuer; never part of a timing assertion. */
  private static final Duration ANSWER = Duration.ofSeconds(30);

  private final SigningIssuer issuer = new SigningIssuer();
  private final VirtualTimeScheduler time = VirtualTimeScheduler.create();
  private final AtomicReference<String> keyEndpoint = new AtomicReference<>(issuer.keyEndpoint());
  private final IssuerSigningKeys keys =
      new IssuerSigningKeys(
          WebClient.create(),
          Mono.fromSupplier(keyEndpoint::get),
          IssuerSigningKeys.KEPT,
          IssuerSigningKeys.RETRY,
          IssuerSigningKeys.FETCH_TIMEOUT,
          IssuerSigningKeys.MAX_AGE,
          time);

  @AfterEach
  void stop() {
    issuer.close();
  }

  @Test
  void aHeldKeyServesItsTokensWithoutAskingTheIssuerAgain() {
    assertThat(keysOf(current())).extracting(JWK::getKeyID).containsExactly("key-1");
    assertThat(issuer.keyRequests()).isEqualTo(1);

    for (int i = 0; i < 20; i++) {
      assertThat(keysOf(current())).hasSize(1);
    }
    // Long after the fetch interval too: a key that is held needs no fetch while its set is
    // younger than the maximum age.
    time.advanceTimeBy(IssuerSigningKeys.MAX_AGE.minusMillis(1));
    assertThat(keysOf(current())).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(1);
  }

  /**
   * R2-2: a key the issuer withdrew (a compromised key rotated out) stops verifying. Before, a held
   * key was served without a request for as long as the process ran.
   */
  @Test
  void aHeldKeyTheIssuerWithdrewStopsVerifyingOnceTheHeldSetIsTooOld() {
    SignedJWT signedWithTheWithdrawnKey = current();
    assertThat(keysOf(signedWithTheWithdrawnKey)).hasSize(1);
    issuer.rotateTo("key-2");

    // Younger than the maximum age, the held set still serves it, without a request.
    time.advanceTimeBy(IssuerSigningKeys.MAX_AGE.minusMillis(1));
    assertThat(keysOf(signedWithTheWithdrawnKey)).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(1);

    // At the maximum age the issuer is asked once, and the key is not in what it publishes.
    time.advanceTimeBy(Duration.ofMillis(1));
    for (int i = 0; i < 20; i++) {
      assertThat(keysOf(signedWithTheWithdrawnKey)).isEmpty();
    }
    assertThat(issuer.keyRequests()).isEqualTo(2);
    // The key the issuer signs with now came with the same fetch.
    assertThat(keysOf(current())).extracting(JWK::getKeyID).containsExactly("key-2");
    assertThat(issuer.keyRequests()).isEqualTo(2);
  }

  /** R2-2: an unchanged set that is too old is fetched again once, and then held again. */
  @Test
  void aHeldSetThatIsTooOldIsFetchedAgainOnceAndHeldAgain() {
    assertThat(keysOf(current())).hasSize(1);
    time.advanceTimeBy(IssuerSigningKeys.MAX_AGE);

    for (int i = 0; i < 20; i++) {
      assertThat(keysOf(current())).extracting(JWK::getKeyID).containsExactly("key-1");
    }
    assertThat(issuer.keyRequests()).isEqualTo(2);
    // The new set has its own age: no request until it is too old in turn.
    time.advanceTimeBy(IssuerSigningKeys.MAX_AGE.minusMillis(1));
    assertThat(keysOf(current())).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(2);
    time.advanceTimeBy(Duration.ofMillis(1));
    assertThat(keysOf(current())).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(3);
  }

  /** R2-2: an outage of the key endpoint does not refuse credentials whose key is held. */
  @Test
  void whenTheRefreshOfATooOldSetFailsTheHeldKeysKeepVerifying() {
    assertThat(keysOf(current())).hasSize(1);
    time.advanceTimeBy(IssuerSigningKeys.MAX_AGE);
    issuer.keysAre(Answer.FAILING);

    for (int i = 0; i < 20; i++) {
      assertThat(keysOf(current())).extracting(JWK::getKeyID).containsExactly("key-1");
    }
    // A token whose key is not held is an outage, not a refusal, and asks for nothing more.
    assertUnavailable(unknown());
    assertThat(issuer.keyRequests()).isEqualTo(2);

    // One request per retry interval while the refresh keeps failing.
    time.advanceTimeBy(IssuerSigningKeys.RETRY.minusMillis(1));
    assertThat(keysOf(current())).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(2);
    time.advanceTimeBy(Duration.ofMillis(1));
    for (int i = 0; i < 20; i++) {
      assertThat(keysOf(current())).hasSize(1);
    }
    assertThat(issuer.keyRequests()).isEqualTo(3);

    // The issuer answers again: the refresh succeeds and the set is young again.
    time.advanceTimeBy(IssuerSigningKeys.RETRY);
    issuer.keysAre(Answer.SERVED);
    assertThat(keysOf(current())).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(4);
    time.advanceTimeBy(IssuerSigningKeys.KEPT);
    assertThat(keysOf(current())).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(4);
  }

  /** R1-3: the key id is the caller's choice, the rate of key requests is not. */
  @Test
  void tokensNamingUnknownKeysCauseAtMostOneFetchPerInterval() {
    // From cold: the first of them fetches, and the fetch answers the rest.
    for (int i = 0; i < 50; i++) {
      assertThat(keysOf(unknown())).isEmpty();
    }
    assertThat(issuer.keyRequests()).isEqualTo(1);

    time.advanceTimeBy(IssuerSigningKeys.KEPT.minusMillis(1));
    assertThat(keysOf(unknown())).isEmpty();
    assertThat(issuer.keyRequests()).isEqualTo(1);

    // The interval has passed: one more fetch, which again answers every token after it.
    time.advanceTimeBy(Duration.ofMillis(1));
    for (int i = 0; i < 50; i++) {
      assertThat(keysOf(unknown())).isEmpty();
    }
    assertThat(issuer.keyRequests()).isEqualTo(2);
  }

  /** Tokens that arrive together wait for the one fetch in flight; none starts another. */
  @Test
  void tokensArrivingWhileAFetchIsUnansweredShareIt() throws Exception {
    issuer.holdKeys();
    List<CompletableFuture<List<JWK>>> waiting = new ArrayList<>();
    for (int i = 0; i < 10; i++) {
      waiting.add(keys.of(unknown()).collectList().toFuture());
    }
    awaitKeyRequests(1);
    assertThat(waiting).noneMatch(CompletableFuture::isDone);

    issuer.releaseKeys();
    for (CompletableFuture<List<JWK>> answer : waiting) {
      assertThat(answer.get(ANSWER.toSeconds(), TimeUnit.SECONDS)).isEmpty();
    }
    assertThat(issuer.keyRequests()).isEqualTo(1);
  }

  @Test
  void aKeyTheIssuerStartsUsingIsAcceptedOnceTheIntervalHasPassed() {
    assertThat(keysOf(current())).hasSize(1);
    issuer.rotateTo("key-2");

    // Inside the interval the new key is unknown and not fetched: its tokens find no key.
    assertThat(keysOf(current())).isEmpty();
    assertThat(issuer.keyRequests()).isEqualTo(1);

    time.advanceTimeBy(IssuerSigningKeys.KEPT);
    assertThat(keysOf(current())).extracting(JWK::getKeyID).containsExactly("key-2");
    assertThat(issuer.keyRequests()).isEqualTo(2);
  }

  /** R1-1: a fetch that fails at once says nothing about the token. */
  @Test
  void aFetchThatFailsIsAnOutageAndIsRepeatedAfterTheRetryInterval(CapturedOutput output) {
    issuer.keysAre(Answer.FAILING);
    for (int i = 0; i < 10; i++) {
      assertUnavailable(current());
    }
    assertThat(issuer.keyRequests()).isEqualTo(1);

    time.advanceTimeBy(IssuerSigningKeys.RETRY.minusMillis(1));
    assertUnavailable(current());
    assertThat(issuer.keyRequests()).isEqualTo(1);

    // The retry interval has passed and the issuer answers again.
    time.advanceTimeBy(Duration.ofMillis(1));
    issuer.keysAre(Answer.SERVED);
    assertThat(keysOf(current())).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(2);
    assertThat(output.getAll())
        .contains("Fetching the issuer's keys failed: ")
        .doesNotContain("\tat ");
  }

  @Test
  void aKeyEndpointThatRefusesTheConnectionIsAnOutage() {
    keyEndpoint.set(StubIdentityProvider.UNREACHABLE + "/certs");
    assertUnavailable(current());
    assertThat(issuer.keyRequests()).isZero();
  }

  @Test
  void tokensWhoseKeyIsHeldAreStillServedWhileTheFetchFails() {
    assertThat(keysOf(current())).hasSize(1);
    time.advanceTimeBy(IssuerSigningKeys.KEPT);
    issuer.keysAre(Answer.FAILING);

    assertUnavailable(unknown());
    assertThat(issuer.keyRequests()).isEqualTo(2);
    // The held key still serves; a token that needs a fetch is an outage without a new request.
    assertThat(keysOf(current())).extracting(JWK::getKeyID).containsExactly("key-1");
    assertUnavailable(unknown());
    assertThat(issuer.keyRequests()).isEqualTo(2);
  }

  /**
   * The price of asking again: past the maximum age a held key waits for the refresh to fail. A key
   * endpoint that never answers holds its tokens until the fetch is given up, and only then do the
   * held keys serve.
   */
  @Test
  void aHeldKeyOfATooOldSetWaitsForAnUnansweredRefreshAndIsServedWhenItIsGivenUp()
      throws Exception {
    SignedJWT token = current();
    assertThat(keysOf(token)).hasSize(1);
    time.advanceTimeBy(IssuerSigningKeys.MAX_AGE);
    issuer.keysAre(Answer.UNANSWERED);

    CompletableFuture<List<JWK>> waiting = keys.of(token).collectList().toFuture();
    awaitKeyRequests(2);
    time.advanceTimeBy(IssuerSigningKeys.FETCH_TIMEOUT.minusMillis(1));
    assertThat(waiting).isNotDone();
    time.advanceTimeBy(Duration.ofMillis(1));

    assertThat(waiting).isDone();
    assertThat(waiting.get(ANSWER.toSeconds(), TimeUnit.SECONDS))
        .extracting(JWK::getKeyID)
        .containsExactly("key-1");
    // For the retry interval after the failure the held key serves at once, without a request.
    assertThat(keysOf(token)).hasSize(1);
    assertThat(issuer.keyRequests()).isEqualTo(2);
  }

  @Test
  void aFetchThatIsNeverAnsweredIsAnOutageWhenItsTimeHasPassed() throws Exception {
    issuer.keysAre(Answer.UNANSWERED);
    CompletableFuture<List<JWK>> waiting = keys.of(current()).collectList().toFuture();
    awaitKeyRequests(1);

    time.advanceTimeBy(IssuerSigningKeys.FETCH_TIMEOUT.minusMillis(1));
    assertThat(waiting).isNotDone();
    time.advanceTimeBy(Duration.ofMillis(1));
    assertThatThrownBy(() -> waiting.get(ANSWER.toSeconds(), TimeUnit.SECONDS))
        .hasCauseInstanceOf(IdentityProviderUnavailableException.class);
  }

  /** What the endpoint said reaches neither the failure nor the log. */
  @Test
  void anAnswerThatIsNotAKeySetIsAnOutageThatCarriesNothingOfIt(CapturedOutput output) {
    issuer.keysAre(Answer.UNUSABLE);
    assertThatThrownBy(() -> keysOf(current()))
        .isInstanceOf(IdentityProviderUnavailableException.class)
        .satisfies(failure -> {
          assertThat(SafeFailure.describe(failure)).doesNotContain(SigningIssuer.UNUSABLE_MARKER);
          for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            assertThat(String.valueOf(cause.getMessage()))
                .doesNotContain(SigningIssuer.UNUSABLE_MARKER);
          }
        });
    assertThat(output.getAll()).doesNotContain(SigningIssuer.UNUSABLE_MARKER);
  }

  @Test
  void aTokenOfAnAlgorithmNoKeyVerifiesAsksForNothing() {
    assertThat(keysOf(parse(unsigned("{\"alg\":\"none-of-ours\",\"kid\":\"key-1\"}")))).isEmpty();
    assertThat(issuer.keyRequests()).isZero();
  }

  @Test
  void theKeysOfAnEarlierKeyEndpointAreNotUsedForANewOne() {
    assertThat(keysOf(current())).hasSize(1);
    // The discovery document now names another address: nothing held for the earlier one counts.
    keyEndpoint.set(StubIdentityProvider.UNREACHABLE + "/certs");
    assertUnavailable(current());
    assertThat(issuer.keyRequests()).isEqualTo(1);
  }

  private List<JWK> keysOf(SignedJWT token) {
    return keys.of(token).collectList().block(ANSWER);
  }

  private void assertUnavailable(SignedJWT token) {
    assertThatThrownBy(() -> keysOf(token))
        .isInstanceOf(IdentityProviderUnavailableException.class);
  }

  /** A token signed with the issuer's current key. */
  private SignedJWT current() {
    return parse(issuer.sign(issuer.claims("owl-mast-web", "subject-1")));
  }

  /** A token that names a key the issuer never published. */
  private SignedJWT unknown() {
    return parse(issuer.signedBySomebodyElse(issuer.claims("owl-mast-web", "subject-1")));
  }

  private void awaitKeyRequests(int count) throws InterruptedException {
    long deadline = System.nanoTime() + ANSWER.toNanos();
    while (issuer.keyRequests() < count && System.nanoTime() < deadline) {
      Thread.sleep(5);
    }
    assertThat(issuer.keyRequests()).isEqualTo(count);
  }

  private static String unsigned(String header) {
    Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
    return encoder.encodeToString(header.getBytes(java.nio.charset.StandardCharsets.UTF_8))
        + "."
        + encoder.encodeToString(
            "{\"sub\":\"x\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8))
        + "."
        + encoder.encodeToString(new byte[] {1, 2, 3});
  }

  private static SignedJWT parse(String token) {
    try {
      return SignedJWT.parse(token);
    } catch (ParseException failure) {
      throw new IllegalStateException(failure);
    }
  }
}
