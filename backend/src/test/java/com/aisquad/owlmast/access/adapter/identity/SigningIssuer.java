package com.aisquad.owlmast.access.adapter.identity;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

/**
 * A local issuer for unit tests that verify signatures: it publishes a discovery document, a key
 * set and a token endpoint, and signs tokens with a key generated for the test. A test chooses how
 * the key and the token endpoint answer and counts the requests they received. Nothing here is a
 * real key, account or credential.
 */
public final class SigningIssuer implements AutoCloseable {

  /** How an endpoint answers. */
  public enum Answer {
    /** The key set, or the token answer the test gave. */
    SERVED,
    /** 503 at once. */
    FAILING,
    /** 200 with a body that is not what was asked for. */
    UNUSABLE,
    /** The request is received and never answered (until the issuer is closed). */
    UNANSWERED
  }

  public static final String PATH = "/realms/owl-mast";

  /** Text an unusable answer carries: it must reach no exception message and no log line. */
  public static final String UNUSABLE_MARKER = "provider-text-marker";

  private final AtomicReference<RSAKey> signing = new AtomicReference<>(generate("key-1"));
  private final AtomicReference<JWKSet> published =
      new AtomicReference<>(new JWKSet(signing.get().toPublicJWK()));
  private final RSAKey foreign = generate("foreign");
  private final AtomicReference<Answer> keys = new AtomicReference<>(Answer.SERVED);
  private final AtomicReference<Answer> tokens = new AtomicReference<>(Answer.SERVED);
  private final AtomicReference<String> tokenAnswer = new AtomicReference<>("{}");
  private final AtomicInteger keyRequests = new AtomicInteger();
  private final AtomicInteger tokenRequests = new AtomicInteger();
  private final Sinks.Empty<Void> closed = Sinks.empty();
  private final AtomicReference<Sinks.Empty<Void>> heldKeys = new AtomicReference<>();
  private final AtomicReference<Mono<Void>> keysGate = new AtomicReference<>(Mono.empty());
  private final DisposableServer server;
  private final String issuer;

  public SigningIssuer() {
    server =
        HttpServer.create()
            .port(0)
            .route(routes ->
                routes
                    .get(
                        PATH + "/.well-known/openid-configuration",
                        (request, response) ->
                            response
                                .header("Content-Type", "application/json")
                                .sendString(Mono.fromSupplier(this::document)))
                    .get(
                        PATH + "/certs",
                        (request, response) -> {
                          keyRequests.incrementAndGet();
                          return switch (keys.get()) {
                            case FAILING -> response.status(503).send();
                            case UNANSWERED ->
                                response.sendString(closed.asMono().then(Mono.<String>empty()));
                            case UNUSABLE ->
                                response
                                    .header("Content-Type", "application/json")
                                    .sendString(Mono.just("{\"" + UNUSABLE_MARKER + "\":1}"));
                            case SERVED ->
                                response
                                    .header("Content-Type", "application/json")
                                    .sendString(
                                        Mono.fromSupplier(() -> published.get().toString())
                                            .delaySubscription(Mono.defer(keysGate::get)));
                          };
                        })
                    .post(
                        PATH + "/token",
                        (request, response) -> {
                          tokenRequests.incrementAndGet();
                          return switch (tokens.get()) {
                            case FAILING -> response.status(503).send();
                            case UNANSWERED ->
                                response.sendString(closed.asMono().then(Mono.<String>empty()));
                            case UNUSABLE ->
                                response
                                    .header("Content-Type", "application/json")
                                    .sendString(Mono.just("{\"" + UNUSABLE_MARKER + "\":1}"));
                            case SERVED ->
                                response
                                    .header("Content-Type", "application/json")
                                    .sendString(Mono.fromSupplier(tokenAnswer::get));
                          };
                        }))
            .bindNow();
    issuer = "http://localhost:" + server.port() + PATH;
  }

  public String issuerUri() {
    return issuer;
  }

  public String tokenEndpoint() {
    return issuer + "/token";
  }

  public String keyEndpoint() {
    return issuer + "/certs";
  }

  /** How the key endpoint answers from now on. */
  public void keysAre(Answer answer) {
    keys.set(answer);
  }

  /** Key requests are received and counted, and answered only by {@link #releaseKeys()}. */
  public void holdKeys() {
    Sinks.Empty<Void> sink = Sinks.empty();
    heldKeys.set(sink);
    keysGate.set(sink.asMono());
  }

  /** Answers the held key requests and stops holding new ones. */
  public void releaseKeys() {
    keysGate.set(Mono.empty());
    Sinks.Empty<Void> sink = heldKeys.getAndSet(null);
    if (sink != null) {
      sink.tryEmitEmpty();
    }
  }

  /** How the token endpoint answers from now on. */
  public void tokensAre(Answer answer) {
    tokens.set(answer);
  }

  /** The body the token endpoint serves. */
  public void tokenAnswer(String json) {
    tokenAnswer.set(json);
  }

  public int keyRequests() {
    return keyRequests.get();
  }

  public int tokenRequests() {
    return tokenRequests.get();
  }

  /**
   * The issuer starts signing with a new key under {@code keyId} and publishes it in place of the
   * earlier one.
   */
  public void rotateTo(String keyId) {
    RSAKey next = generate(keyId);
    signing.set(next);
    published.set(new JWKSet(next.toPublicJWK()));
  }

  /** A token the issuer signed with its current key. */
  public String sign(Consumer<JWTClaimsSet.Builder> claims) {
    RSAKey key = signing.get();
    return serialize(key, key.getKeyID(), claims);
  }

  /**
   * A token that names a key id the issuer never published and is signed by a key that is not the
   * issuer's: what anybody can send.
   */
  public String signedBySomebodyElse(Consumer<JWTClaimsSet.Builder> claims) {
    return serialize(foreign, "unknown-" + UUID.randomUUID(), claims);
  }

  /** A token that names the issuer's current key id and is signed by a key that is not that key. */
  public String forged(Consumer<JWTClaimsSet.Builder> claims) {
    return serialize(foreign, signing.get().getKeyID(), claims);
  }

  /** Claims of a current token of this issuer for {@code audience}, naming {@code subject}. */
  public Consumer<JWTClaimsSet.Builder> claims(String audience, String subject) {
    Instant now = Instant.now();
    return claims ->
        claims
            .issuer(issuer)
            .subject(subject)
            .audience(audience)
            .issueTime(Date.from(now))
            .expirationTime(Date.from(now.plusSeconds(300)));
  }

  @Override
  public void close() {
    releaseKeys();
    closed.tryEmitEmpty();
    server.disposeNow();
  }

  private String document() {
    return "{\"issuer\":\""
        + issuer
        + "\",\"authorization_endpoint\":\""
        + issuer
        + "/auth\",\"token_endpoint\":\""
        + tokenEndpoint()
        + "\",\"jwks_uri\":\""
        + keyEndpoint()
        + "\"}";
  }

  private static String serialize(RSAKey key, String keyId, Consumer<JWTClaimsSet.Builder> claims) {
    JWTClaimsSet.Builder builder = new JWTClaimsSet.Builder();
    claims.accept(builder);
    SignedJWT token =
        new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(keyId).type(JOSEObjectType.JWT).build(),
            builder.build());
    try {
      token.sign(new RSASSASigner(key));
    } catch (JOSEException failure) {
      throw new IllegalStateException(failure);
    }
    return token.serialize();
  }

  private static RSAKey generate(String keyId) {
    try {
      return new RSAKeyGenerator(2048).keyID(keyId).generate();
    } catch (JOSEException failure) {
      throw new IllegalStateException(failure);
    }
  }
}
