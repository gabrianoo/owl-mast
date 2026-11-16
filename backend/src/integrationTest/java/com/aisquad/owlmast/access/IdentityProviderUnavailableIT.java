package com.aisquad.owlmast.access;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.fixtures.security.SyntheticBrowser;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.net.URI;
import java.net.http.HttpResponse;
import java.time.Duration;
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

/**
 * OM-02.01, "identity provider unavailable": the issuer here answers discovery without a token or
 * key endpoint, so it cannot serve a sign-in or verify a credential. Every step that needs it
 * answers 5xx without anything the provider said, leaves no session, and is recorded as a failed
 * sign-in; what needs no provider keeps working.
 */
@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
@Import({ContainersConfiguration.class, StubIdentityConfiguration.class})
@ExtendWith(OutputCaptureExtension.class)
class IdentityProviderUnavailableIT {

  @LocalServerPort private int port;
  @Autowired private DatabaseClient database;

  @Test
  void startingASignInAnswersUnavailableAndLeavesNoSession(CapturedOutput output) {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    long before = failedSignIns();

    // A browser navigation returns to the shell, which shows its provider-error state.
    HttpResponse<String> navigation = browser.get("/api/session/sign-in", "Accept", "text/html");
    assertThat(navigation.statusCode()).isEqualTo(303);
    assertThat(SyntheticBrowser.location(navigation))
        .isEqualTo(URI.create("http://localhost:8080/?sign-in=unavailable"));

    // Any other caller gets the status in the envelope.
    HttpResponse<String> api = browser.get("/api/session/sign-in");
    assertThat(api.statusCode()).isEqualTo(503);
    assertThat(api.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(api.body())
        .contains("\"status\":503")
        .doesNotContain("detail")
        .doesNotContain("localhost")
        .doesNotContain("Exception");

    assertThat(browser.backendCookies()).isEmpty();
    assertThat(browser.get("/api/session").body()).contains("signed-out");
    assertThat(failedSignIns()).isEqualTo(before + 2);
    assertThat(output.getAll())
        .contains("Sign-in did not complete (outage)")
        .doesNotContain("\tat ");
  }

  @Test
  void aBearerCredentialThatCannotBeVerifiedIsNotAccepted() {
    HttpResponse<String> answer =
        new SyntheticBrowser(port).get("/api/anything", "Authorization", "Bearer not-verifiable");
    assertThat(answer.statusCode()).isEqualTo(503);
    assertThat(answer.headers().firstValue("Content-Type")).contains("application/problem+json");
    assertThat(answer.body()).doesNotContain("detail").doesNotContain("Exception");
  }

  @Test
  void whatNeedsNoProviderKeepsWorking() {
    SyntheticBrowser browser = new SyntheticBrowser(port);
    assertThat(browser.get("/api/compatibility").statusCode()).isEqualTo(200);
    assertThat(browser.get("/actuator/health/liveness").statusCode()).isEqualTo(200);
    assertThat(browser.get("/api/session").statusCode()).isEqualTo(200);
    // A protected call without a credential is still a plain 401.
    assertThat(browser.get("/api/anything").statusCode()).isEqualTo(401);
  }

  /** Failed sign-ins: FAILED, nobody bound, and the reason is exception class names only. */
  private long failedSignIns() {
    Long count =
        database
            .sql(
                """
                select count(*) as n from audit.event
                 where action = 'session.sign-in' and outcome = 'FAILED' and actor_id is null
                   and reason like 'IdentityProviderUnavailableException%'
                """)
            .map(row -> row.get("n", Long.class))
            .one()
            .block(Duration.ofSeconds(10));
    return count == null ? 0 : count;
  }
}
