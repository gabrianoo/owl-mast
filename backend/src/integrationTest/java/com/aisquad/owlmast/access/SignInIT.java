package com.aisquad.owlmast.access;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.fixtures.security.SyntheticBrowser;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.SyntheticKeycloak;
import com.aisquad.owlmast.testing.SyntheticKeycloakConfiguration;
import java.net.URI;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Supplier;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.testcontainers.Testcontainers;
import reactor.core.publisher.Mono;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * OM-02.01 against the pinned Keycloak with a synthetic realm and synthetic people: every row of
 * the spec's matrix that needs a real identity provider. The "browser" follows the redirects and
 * fills in Keycloak's own login form; the protected operations are test-only endpoints behind the
 * production security chain (nothing opens a path here).
 *
 * <p>Access tokens live thirty seconds in this realm, which is inside the minute before expiry in
 * which the backend renews: every request asks Keycloak whether the session still stands.
 */
@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = "owlmast.fixture.access-token-lifespan=PT30S")
@Import({
  ContainersConfiguration.class,
  SyntheticKeycloakConfiguration.class,
  SignInIT.ProtectedOperations.class
})
@ExtendWith(OutputCaptureExtension.class)
class SignInIT {

  private static final String WHO_AM_I = "/api/test-only/who-am-i";
  private static final JsonMapper JSON = JsonMapper.builder().build();

  @LocalServerPort private int port;
  @Autowired private SyntheticKeycloak keycloak;
  @Autowired private DatabaseClient database;

  @AfterEach
  void keycloakTellsNobody() {
    keycloak.announceLogoutsTo(Optional.empty());
  }

  @Test
  void aPersonSignsInAndIsBoundToIssuerAndSubject(CapturedOutput output) {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    assertThat(json(browser.get("/api/session")).get("state").asString()).isEqualTo("signed-out");
    long signInsBefore = signIns();

    // The authorization request carries a state, a nonce and a PKCE challenge, and returns to
    // the configured application origin.
    HttpResponse<String> start =
        new SyntheticBrowser(port).get("/api/session/sign-in", "Accept", "text/html");
    assertThat(start.statusCode()).isEqualTo(302);
    assertThat(SyntheticBrowser.location(start).toString())
        .startsWith(keycloak.issuerUri() + "/protocol/openid-connect/auth?")
        .contains("response_type=code")
        .contains("client_id=" + SyntheticKeycloak.CLIENT_ID)
        .contains("state=")
        .contains("nonce=")
        .contains("code_challenge=")
        .contains("code_challenge_method=S256")
        .contains("redirect_uri=http://localhost:8080/api/session/callback")
        .doesNotContain(keycloak.clientSecret());

    HttpResponse<String> returned = browser.signIn(keycloak, SyntheticKeycloak.ADA);

    // Returned to the shell on the application origin, with nothing in the address.
    assertThat(returned.statusCode()).isEqualTo(302);
    assertThat(SyntheticBrowser.location(returned)).isEqualTo(URI.create("http://localhost:8080/"));

    JsonNode session = json(browser.get("/api/session"));
    assertThat(session.get("state").asString()).isEqualTo("signed-in");
    assertThat(session.get("person").get("displayName").asString()).isEqualTo("Ada Synthetic");
    String principalId = session.get("person").get("principalId").asString();
    assertThat(session.get("person").propertyNames())
        .containsExactlyInAnyOrder("principalId", "displayName");
    assertThat(session.get("csrf").get("headerName").asString()).isEqualTo("X-CSRF-TOKEN");

    // The principal is the pair (issuer, subject) and nothing else was stored about the person.
    Map<String, Object> principal = principalRow(principalId);
    assertThat(principal)
        .containsEntry("issuer", keycloak.issuerUri())
        .containsEntry("subject", keycloak.subjectOf(SyntheticKeycloak.ADA))
        .containsEntry("tenant_id", "default");
    assertThat(principal.keySet())
        .containsExactlyInAnyOrder(
            "principal_id",
            "tenant_id",
            "issuer",
            "subject",
            "created_at",
            "last_sign_in_at",
            "sign_in_count");

    // The scope of a protected operation is that principal in the installation's tenant.
    JsonNode who = json(browser.get(WHO_AM_I));
    assertThat(who.get("principal").asString()).isEqualTo(principalId);
    assertThat(who.get("tenant").asString()).isEqualTo("default");

    // The outcome is recorded once, with the person as actor.
    assertThat(signIns()).isEqualTo(signInsBefore + 1);
    assertThat(outcomes("session.sign-in", principalId))
        .isNotEmpty()
        .containsOnly(
            Map.of("outcome", "SUCCEEDED", "actor_kind", "HUMAN", "object_type", "session"));

    // The cookie is set when the sign-in starts and replaced when it completes, and never again:
    // requests the shell sends side by side after the return all carry an id that stays valid.
    assertThat(browser.backendSetCookies()).hasSize(2);
    String sessionId = browser.sessionCookie();
    for (int read = 0; read < 3; read++) {
      assertThat(json(browser.get("/api/session")).get("state").asString()).isEqualTo("signed-in");
    }
    assertThat(browser.backendSetCookies()).hasSize(2);
    assertThat(browser.sessionCookie()).isEqualTo(sessionId);

    // One cookie, HttpOnly, Secure, SameSite=Lax, and no token anywhere the browser can see.
    assertThat(browser.backendCookies()).containsOnlyKeys("OWLMAST_SESSION");
    assertThat(browser.backendSetCookies())
        .isNotEmpty()
        .allSatisfy(cookie ->
            assertThat(cookie)
                .startsWith("OWLMAST_SESSION=")
                .containsIgnoringCase("HttpOnly")
                .contains("Secure")
                .contains("SameSite=Lax")
                .contains("Path=/api"));
    assertNoCredentialIn(browser.everythingTheBackendSent());
    assertNoCredentialIn(output.getAll());
    assertThat(output.getAll()).doesNotContain(keycloak.userPassword());
  }

  @Test
  void theSamePersonKeepsThePrincipalWhenTheDisplayNameChanges() {
    SyntheticBrowser first = new SyntheticBrowser(port);
    first.signIn(keycloak, SyntheticKeycloak.GRACE);
    JsonNode before = json(first.get("/api/session")).get("person");
    long signInsBefore =
        (Long) principalRow(before.get("principalId").asString()).get("sign_in_count");

    keycloak.rename(SyntheticKeycloak.GRACE, "Grace Brewster", "Renamed");
    try {
      SyntheticBrowser second = new SyntheticBrowser(port);
      second.signIn(keycloak, SyntheticKeycloak.GRACE);
      JsonNode after = json(second.get("/api/session")).get("person");

      assertThat(after.get("displayName").asString()).isEqualTo("Grace Brewster Renamed");
      assertThat(after.get("principalId").asString())
          .isEqualTo(before.get("principalId").asString());
      assertThat(principalRow(after.get("principalId").asString()).get("sign_in_count"))
          .isEqualTo(signInsBefore + 1);
      // A second person is another principal.
      SyntheticBrowser other = new SyntheticBrowser(port);
      other.signIn(keycloak, SyntheticKeycloak.ADA);
      assertThat(json(other.get("/api/session")).get("person").get("principalId").asString())
          .isNotEqualTo(after.get("principalId").asString());
    } finally {
      keycloak.rename(SyntheticKeycloak.GRACE, "Grace", "Synthetic");
    }
  }

  @Test
  void aProtectedCallWithoutACredentialIsUnauthorizedAndNeverRedirected() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    for (String accept : List.of("application/json", "text/html")) {
      HttpResponse<String> answer = browser.get(WHO_AM_I, "Accept", accept);
      assertThat(answer.statusCode()).isEqualTo(401);
      assertThat(answer.headers().firstValue("Location")).isEmpty();
      assertThat(answer.headers().firstValue("WWW-Authenticate")).contains("Bearer");
      assertThat(answer.headers().firstValue("Content-Type")).contains("application/problem+json");
      assertThat(json(answer).get("status").asInt()).isEqualTo(401);
      assertThat(json(answer).has("detail")).isFalse();
    }
    // No session was created for the refusal.
    assertThat(browser.backendCookies()).isEmpty();
  }

  @Test
  void publicEndpointsNeedNoCredential() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    assertThat(browser.get("/api/compatibility").statusCode()).isEqualTo(200);
    assertThat(browser.get("/actuator/health").statusCode()).isEqualTo(200);
    assertThat(browser.get("/actuator/health/readiness").statusCode()).isEqualTo(200);
    assertThat(browser.get("/actuator/health/liveness").statusCode()).isEqualTo(200);
    assertThat(browser.get("/api/session").statusCode()).isEqualTo(200);
    assertThat(browser.backendCookies()).isEmpty();
  }

  @Test
  void anUnsafeCallNeedsTheCsrfTokenAndSignOutEndsBothSessions() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.ADA);
    JsonNode session = json(browser.get("/api/session"));
    String principalId = session.get("person").get("principalId").asString();
    String header = session.get("csrf").get("headerName").asString();
    String token = session.get("csrf").get("token").asString();
    assertThat(keycloak.sessionsOf(SyntheticKeycloak.ADA)).isPositive();
    // The token is masked anew for every read; each masked value is accepted.
    assertThat(json(browser.get("/api/session")).get("csrf").get("token").asString())
        .isNotEqualTo(token);
    int before = outcomes("session.sign-out", principalId).size();
    int changesBefore = ProtectedOperations.changes.get();

    // Without the token: 403, and nothing happened.
    for (String path : List.of("/api/session/sign-out", "/api/test-only/change")) {
      HttpResponse<String> refused = browser.post(path, "");
      assertThat(refused.statusCode()).isEqualTo(403);
      assertThat(refused.headers().firstValue("Content-Type")).contains("application/problem+json");
      assertThat(json(refused).get("status").asInt()).isEqualTo(403);
    }
    assertThat(browser.post("/api/session/sign-out", "", header, "not-the-token").statusCode())
        .isEqualTo(403);
    assertThat(ProtectedOperations.changes.get()).isEqualTo(changesBefore);
    assertThat(json(browser.get("/api/session")).get("state").asString()).isEqualTo("signed-in");

    // With it the unsafe call runs, and sign-out ends the session here and in Keycloak.
    assertThat(browser.post("/api/test-only/change", "", header, token).statusCode())
        .isEqualTo(200);
    assertThat(ProtectedOperations.changes.get()).isEqualTo(changesBefore + 1);
    HttpResponse<String> signedOut = browser.post("/api/session/sign-out", "", header, token);
    assertThat(signedOut.statusCode()).isEqualTo(200);
    assertThat(json(signedOut).get("state").asString()).isEqualTo("signed-out");
    assertThat(json(signedOut).get("identityProvider").asString()).isEqualTo("ended");
    assertThat(browser.backendCookies()).isEmpty();
    assertThat(keycloak.sessionsOf(SyntheticKeycloak.ADA)).isZero();
    assertThat(json(browser.get("/api/session")).get("state").asString()).isEqualTo("signed-out");
    assertThat(browser.get(WHO_AM_I).statusCode()).isEqualTo(401);
    assertThat(outcomes("session.sign-out", principalId)).hasSize(before + 1);
    assertNoCredentialIn(browser.everythingTheBackendSent());
  }

  @Test
  void theOldCookieOfASignedOutSessionIsWorthNothing() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.ADA);
    String cookie = "OWLMAST_SESSION=" + browser.sessionCookie();
    JsonNode csrf = json(browser.get("/api/session")).get("csrf");
    browser.post(
        "/api/session/sign-out",
        "",
        csrf.get("headerName").asString(),
        csrf.get("token").asString());

    SyntheticBrowser replay = new SyntheticBrowser(port);
    assertThat(replay.get(WHO_AM_I, "Cookie", cookie).statusCode()).isEqualTo(401);
    assertThat(json(replay.get("/api/session", "Cookie", cookie)).get("state").asString())
        .isEqualTo("signed-out");
  }

  @Test
  void aSessionKeycloakNoLongerRenewsIsDeniedAtTheNextOperation() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.GRACE);
    String principalId =
        json(browser.get("/api/session")).get("person").get("principalId").asString();
    assertThat(browser.get(WHO_AM_I).statusCode()).isEqualTo(200);
    int before = outcomes("session.expire", principalId).size();

    // The session ends in Keycloak and nobody is told: the backend finds out when it renews.
    keycloak.endSessionsOf(SyntheticKeycloak.GRACE);

    HttpResponse<String> denied = browser.get(WHO_AM_I);
    assertThat(denied.statusCode()).isEqualTo(401);
    assertThat(denied.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(denied.body()).doesNotContain(principalId).doesNotContain("Grace");
    assertThat(json(browser.get("/api/session")).get("state").asString()).isEqualTo("signed-out");
    // A public endpoint is still served to the same browser.
    assertThat(browser.get("/api/compatibility").statusCode()).isEqualTo(200);
    assertThat(outcomes("session.expire", principalId)).hasSize(before + 1);
  }

  @Test
  void aSessionRevokedInKeycloakIsDeniedAtOnce() {
    Testcontainers.exposeHostPorts(port);
    keycloak.announceLogoutsTo(
        Optional.of(
            "http://host.testcontainers.internal:" + port + "/api/session/backchannel-logout"));
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.GRACE);
    SyntheticBrowser other = new SyntheticBrowser(port);
    other.signIn(keycloak, SyntheticKeycloak.ADA);
    String principalId =
        json(browser.get("/api/session")).get("person").get("principalId").asString();
    int before = outcomes("session.revoke", principalId).size();

    // An administrator ends the person's sessions; Keycloak posts its logout notice.
    keycloak.endSessionsOf(SyntheticKeycloak.GRACE);

    // The notice, not a renewal, ended the session: the record says "revoke".
    assertThat(eventually(() -> outcomes("session.revoke", principalId).size() == before + 1))
        .as("the logout notice ended the session")
        .isTrue();
    assertThat(browser.get(WHO_AM_I).statusCode()).isEqualTo(401);
    assertThat(json(browser.get("/api/session")).get("state").asString()).isEqualTo("signed-out");
    assertThat(outcomes("session.expire", principalId)).isEmpty();
    // Another person's session is untouched.
    assertThat(other.get(WHO_AM_I).statusCode()).isEqualTo(200);
  }

  @Test
  void aLogoutNoticeThatKeycloakDidNotSignChangesNothing() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.ADA);
    // A token of the realm that is not a logout token, a token of another realm, and no token.
    for (String notice :
        List.of(
            keycloak.accessToken(
                SyntheticKeycloak.REALM, SyntheticKeycloak.BEARER_CLIENT, SyntheticKeycloak.ADA),
            keycloak.accessToken(
                SyntheticKeycloak.OTHER_REALM,
                SyntheticKeycloak.BEARER_CLIENT,
                SyntheticKeycloak.ADA),
            "not-a-token",
            "")) {
      HttpResponse<String> refused =
          new SyntheticBrowser(port)
              .post(
                  "/api/session/backchannel-logout",
                  "logout_token=" + notice,
                  "Content-Type",
                  "application/x-www-form-urlencoded");
      assertThat(refused.statusCode()).isEqualTo(400);
      assertThat(refused.headers().firstValue("Content-Type")).contains("application/problem+json");
    }
    assertThat(browser.get(WHO_AM_I).statusCode()).isEqualTo(200);
  }

  @Test
  void aBearerCredentialIsCheckedForIssuerAndAudienceAndBoundToTheSamePrincipal() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.ADA);
    String principalId =
        json(browser.get("/api/session")).get("person").get("principalId").asString();

    // This realm, this audience: accepted, and it is the same principal as the browser session.
    String accepted =
        keycloak.accessToken(
            SyntheticKeycloak.REALM, SyntheticKeycloak.BEARER_CLIENT, SyntheticKeycloak.ADA);
    HttpResponse<String> who = bearer(WHO_AM_I, accepted);
    assertThat(who.statusCode()).isEqualTo(200);
    assertThat(json(who).get("principal").asString()).isEqualTo(principalId);
    // A bearer call has no browser session and takes no cookie.
    assertThat(who.headers().allValues("Set-Cookie")).isEmpty();

    // Another client's audience, another realm, and something that is not a credential.
    Map<String, String> refused =
        Map.of(
            keycloak.accessToken(
                SyntheticKeycloak.REALM,
                SyntheticKeycloak.OTHER_AUDIENCE_CLIENT,
                SyntheticKeycloak.ADA),
            "credential-audience-mismatch",
            keycloak.accessToken(
                SyntheticKeycloak.OTHER_REALM,
                SyntheticKeycloak.BEARER_CLIENT,
                SyntheticKeycloak.ADA),
            "credential-invalid",
            "not-a-credential",
            "credential-invalid");
    refused.forEach((credential, reason) -> {
      int before = refusals(reason);
      HttpResponse<String> answer = bearer(WHO_AM_I, credential);
      assertThat(answer.statusCode()).as(reason).isEqualTo(401);
      assertThat(answer.headers().firstValue("WWW-Authenticate"))
          .contains("Bearer error=\"invalid_token\"");
      assertThat(answer.headers().firstValue("Content-Type")).contains("application/problem+json");
      // Neither the reason nor anything about the credential is in the answer.
      assertThat(answer.body()).doesNotContain("audience").doesNotContain("issuer");
      assertThat(json(answer).has("detail")).isFalse();
      assertThat(refusals(reason)).as(reason).isEqualTo(before + 1);
    });
    // Public endpoints do not look at a credential they do not need... but a refused one is
    // still refused: a caller that presents a credential gets a verdict on it.
    assertThat(bearer("/api/compatibility", "not-a-credential").statusCode()).isEqualTo(401);
  }

  @Test
  void aSignedInCallerGetsTheEnvelopeForUnknownPathsAndDenials() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.ADA);
    int refusedCredentials = refusals("credential-invalid");
    int refusedSignIns = refusedSignIns("sign-in-refused");

    HttpResponse<String> unknown = browser.get("/api/does-not-exist");
    assertThat(unknown.statusCode()).isEqualTo(404);
    assertThat(unknown.headers().firstValue("Content-Type")).contains("application/problem+json");

    HttpResponse<String> denied = browser.get("/api/test-only/denied");
    assertThat(denied.statusCode()).isEqualTo(403);
    assertThat(denied.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(denied.body()).doesNotContain("s3cr3t");

    HttpResponse<String> unauthenticated = browser.get("/api/test-only/unauthenticated");
    assertThat(unauthenticated.statusCode()).isEqualTo(401);
    assertThat(unauthenticated.headers().firstValue("WWW-Authenticate")).contains("Bearer");
    assertThat(unauthenticated.body()).doesNotContain("s3cr3t");
    // A failure raised by an operation is not a refused credential and not a refused sign-in.
    assertThat(refusals("credential-invalid")).isEqualTo(refusedCredentials);
    assertThat(refusedSignIns("sign-in-refused")).isEqualTo(refusedSignIns);
  }

  @Test
  void aCallbackNobodyStartedIsRefusedWithoutASession() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    int before = refusedSignIns("authorization-response-unmatched");

    HttpResponse<String> navigation =
        browser.get("/api/session/callback?code=made-up&state=made-up", "Accept", "text/html");
    assertThat(navigation.statusCode()).isEqualTo(303);
    assertThat(SyntheticBrowser.location(navigation))
        .isEqualTo(URI.create("http://localhost:8080/?sign-in=failed"));
    HttpResponse<String> api = browser.get("/api/session/callback?code=made-up&state=made-up");
    assertThat(api.statusCode()).isEqualTo(401);
    assertThat(api.headers().firstValue("Content-Type")).contains("application/problem+json");

    assertThat(browser.backendCookies()).isEmpty();
    assertThat(json(browser.get("/api/session")).get("state").asString()).isEqualTo("signed-out");
    assertThat(refusedSignIns("authorization-response-unmatched")).isEqualTo(before + 2);
  }

  /**
   * A bearer call carries no ambient authority, so it needs no CSRF token; an invalid credential is
   * still refused before anything runs. It has no browser session to sign out of.
   */
  @Test
  void aBearerCallNeedsNoCsrfTokenAndHasNoSessionToSignOutOf() {
    String accepted =
        keycloak.accessToken(
            SyntheticKeycloak.REALM, SyntheticKeycloak.BEARER_CLIENT, SyntheticKeycloak.ADA);
    int changesBefore = ProtectedOperations.changes.get();

    HttpResponse<String> changed =
        new SyntheticBrowser(port)
            .post("/api/test-only/change", "", "Authorization", "Bearer " + accepted);
    assertThat(changed.statusCode()).isEqualTo(200);
    assertThat(ProtectedOperations.changes.get()).isEqualTo(changesBefore + 1);

    HttpResponse<String> refused =
        new SyntheticBrowser(port)
            .post("/api/test-only/change", "", "Authorization", "Bearer not-a-credential");
    assertThat(refused.statusCode()).isEqualTo(401);
    assertThat(refused.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(ProtectedOperations.changes.get()).isEqualTo(changesBefore + 1);

    HttpResponse<String> signOut =
        new SyntheticBrowser(port)
            .post("/api/session/sign-out", "", "Authorization", "Bearer " + accepted);
    assertThat(signOut.statusCode()).isEqualTo(409);
    assertThat(signOut.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(signOut.headers().allValues("Set-Cookie")).isEmpty();
  }

  /** One sign-in per browser session, and a failed callback does not end a session. */
  @Test
  void aSignedInBrowserStartsNoSecondSignInAndAFailedCallbackLeavesItSignedIn() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    browser.signIn(keycloak, SyntheticKeycloak.ADA);
    JsonNode person = json(browser.get("/api/session")).get("person");
    long signIns = signIns();

    HttpResponse<String> again = browser.get("/api/session/sign-in", "Accept", "text/html");
    assertThat(again.statusCode()).isEqualTo(302);
    assertThat(SyntheticBrowser.location(again)).isEqualTo(URI.create("http://localhost:8080/"));

    // Anyone can send a browser to the callback address with a made-up answer.
    HttpResponse<String> forged =
        browser.get("/api/session/callback?code=made-up&state=made-up", "Accept", "text/html");
    assertThat(forged.statusCode()).isEqualTo(303);

    assertThat(json(browser.get("/api/session")).get("person")).isEqualTo(person);
    assertThat(browser.get(WHO_AM_I).statusCode()).isEqualTo(200);
    assertThat(signIns()).isEqualTo(signIns);
  }

  private HttpResponse<String> bearer(String path, String credential) {
    return new SyntheticBrowser(port).get(path, "Authorization", "Bearer " + credential);
  }

  private static JsonNode json(HttpResponse<String> answer) {
    return JSON.readTree(answer.body());
  }

  /** Access, ID and refresh tokens of Keycloak are JWTs; none may reach the browser or the log. */
  private static void assertNoCredentialIn(String text) {
    assertThat(text)
        .doesNotContain("eyJ")
        .doesNotContain("access_token")
        .doesNotContain("id_token");
  }

  private Map<String, Object> principalRow(String principalId) {
    return database
        .sql("select * from access.principal where principal_id = :id")
        .bind("id", java.util.UUID.fromString(principalId.substring("person:".length())))
        .fetch()
        .one()
        .block(Duration.ofSeconds(10));
  }

  /** Recorded outcomes of an action for an actor: published history and pending intents. */
  private List<Map<String, Object>> outcomes(String action, String actorId) {
    return database
        .sql(
            """
            select outcome, actor_kind, object_type from audit.event
             where action = :action and actor_id = :actor
            union all
            select outcome, actor_kind, object_type from audit.publication_intent
             where action = :action and actor_id = :actor and published_at is null
            """)
        .bind("action", action)
        .bind("actor", actorId)
        .fetch()
        .all()
        .collectList()
        .block(Duration.ofSeconds(10));
  }

  /** Every recorded completed sign-in, published or still pending publication. */
  private long signIns() {
    Long count =
        database
            .sql(
                """
                select (select count(*) from audit.event
                         where action = 'session.sign-in' and outcome = 'SUCCEEDED')
                     + (select count(*) from audit.publication_intent
                         where action = 'session.sign-in' and published_at is null) as n
                """)
            .map(row -> row.get("n", Long.class))
            .one()
            .block(Duration.ofSeconds(10));
    return count == null ? 0 : count;
  }

  /** Refused credentials recorded under a reason: DENIED, no actor, nothing about the token. */
  private int refusals(String reason) {
    return unsuccessful("credential.verify", "credential", reason);
  }

  private int refusedSignIns(String reason) {
    return unsuccessful("session.sign-in", "session", reason);
  }

  private int unsuccessful(String action, String objectType, String reason) {
    Long count =
        database
            .sql(
                """
                select count(*) as n from audit.event
                 where action = :action and object_type = :type and outcome = 'DENIED'
                   and reason = :reason and actor_kind = 'HUMAN' and actor_id is null
                   and object_id is null
                """)
            .bind("action", action)
            .bind("type", objectType)
            .bind("reason", reason)
            .map(row -> row.get("n", Long.class))
            .one()
            .block(Duration.ofSeconds(10));
    return count == null ? 0 : count.intValue();
  }

  private static boolean eventually(Supplier<Boolean> condition) {
    long deadline = System.nanoTime() + Duration.ofSeconds(20).toNanos();
    while (System.nanoTime() < deadline) {
      if (condition.get()) {
        return true;
      }
      try {
        Thread.sleep(100);
      } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        return false;
      }
    }
    return condition.get();
  }

  /** Protected operations that exist only in this test, behind the production security chain. */
  @RestController
  static class ProtectedOperations {

    static final java.util.concurrent.atomic.AtomicInteger changes =
        new java.util.concurrent.atomic.AtomicInteger();

    @GetMapping("/api/test-only/who-am-i")
    Mono<Map<String, String>> whoAmI() {
      return Scopes.current()
          .map(scope ->
              Map.of("tenant", scope.tenant().value(), "principal", scope.principal().value()));
    }

    @PostMapping("/api/test-only/change")
    Mono<Map<String, Integer>> change() {
      return Mono.fromSupplier(() -> Map.of("changes", changes.incrementAndGet()));
    }

    @GetMapping("/api/test-only/denied")
    Mono<String> denied() {
      return Mono.error(new AccessDeniedException("s3cr3t"));
    }

    @GetMapping("/api/test-only/unauthenticated")
    Mono<String> unauthenticated() {
      return Mono.error(new BadCredentialsException("s3cr3t"));
    }
  }
}
