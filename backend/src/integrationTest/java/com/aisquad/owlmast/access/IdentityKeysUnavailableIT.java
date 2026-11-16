package com.aisquad.owlmast.access;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.fixtures.security.SyntheticBrowser;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import com.aisquad.owlmast.testing.StubIdentityProvider;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import org.junit.jupiter.api.AfterAll;
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
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * PR #194 review, R1-1: the issuer's discovery document is accepted and its key endpoint refuses
 * the connection, as when the identity provider goes away while the backend holds its document. A
 * credential that needs the keys can then be neither accepted nor refused: a logout notice and a
 * bearer call both answer 503, the notice so that the provider sends it again, and neither is
 * recorded as a refusal.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import(ContainersConfiguration.class)
@ExtendWith(OutputCaptureExtension.class)
class IdentityKeysUnavailableIT {

  private static final StubIdentityProvider PROVIDER =
      StubIdentityProvider.startWithUnreachableEndpoints("owl-mast");

  @LocalServerPort private int port;
  @Autowired private DatabaseClient database;

  @DynamicPropertySource
  static void issuer(DynamicPropertyRegistry registry) {
    registry.add("owlmast.identity.issuer-uri", PROVIDER::issuerUri);
    registry.add("owlmast.identity.allow-insecure-issuer", () -> "true");
    StubIdentityConfiguration.registerSignIn(registry);
  }

  @AfterAll
  static void stop() {
    PROVIDER.close();
  }

  @Test
  void aLogoutNoticeAnswersUnavailableSoThatTheProviderSendsItAgain(CapturedOutput output) {
    HttpResponse<String> answer =
        new SyntheticBrowser(port)
            .post(
                "/api/session/backchannel-logout",
                "logout_token=" + token(),
                "Content-Type",
                "application/x-www-form-urlencoded");

    assertThat(answer.statusCode()).isEqualTo(503);
    assertThat(answer.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(answer.body())
        .contains("\"status\":503")
        .doesNotContain("detail")
        .doesNotContain("127.0.0.1")
        .doesNotContain("Exception");
    assertThat(output.getAll())
        .contains("Logout notice could not be verified")
        .doesNotContain("Logout notice refused")
        .doesNotContain("\tat ");
  }

  @Test
  void aBearerCallAnswersUnavailableAndIsNotRecordedAsARefusal() {
    long before = refusedCredentials();

    HttpResponse<String> answer =
        new SyntheticBrowser(port).get("/api/anything", "Authorization", "Bearer " + token());

    assertThat(answer.statusCode()).isEqualTo(503);
    assertThat(answer.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(answer.body())
        .contains("\"status\":503")
        .doesNotContain("detail")
        .doesNotContain("127.0.0.1")
        .doesNotContain("Exception");
    assertThat(refusedCredentials()).isEqualTo(before);
  }

  /** The document is accepted, so the sign-in can start; what needs no keys keeps working. */
  @Test
  void theDiscoveryDocumentIsAcceptedAndWhatNeedsNoKeysKeepsWorking() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    HttpResponse<String> signIn = browser.get("/api/session/sign-in", "Accept", "text/html");
    assertThat(signIn.statusCode()).isEqualTo(302);
    assertThat(SyntheticBrowser.location(signIn).toString())
        .startsWith(PROVIDER.issuerUri() + "/protocol/openid-connect/auth");
    assertThat(browser.get("/actuator/health/readiness").statusCode()).isEqualTo(200);
    assertThat(browser.get("/api/compatibility").statusCode()).isEqualTo(200);
    assertThat(browser.get("/api/anything").statusCode()).isEqualTo(401);
  }

  /**
   * A token in the compact form with an RS256 header naming a key: what the backend needs the
   * issuer's keys for. Its signature is three arbitrary bytes; nobody signed it.
   */
  private static String token() {
    Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
    return encoder.encodeToString(
            "{\"alg\":\"RS256\",\"typ\":\"JWT\",\"kid\":\"synthetic\"}"
                .getBytes(StandardCharsets.UTF_8))
        + "."
        + encoder.encodeToString("{\"sub\":\"synthetic\"}".getBytes(StandardCharsets.UTF_8))
        + "."
        + encoder.encodeToString(new byte[] {1, 2, 3});
  }

  private long refusedCredentials() {
    Long count =
        database
            .sql("select count(*) as n from audit.event where action = 'credential.verify'")
            .map(row -> row.get("n", Long.class))
            .one()
            .block(Duration.ofSeconds(10));
    return count == null ? 0 : count;
  }
}
