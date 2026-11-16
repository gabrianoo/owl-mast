package com.aisquad.owlmast.access.adapter.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class SignInPropertiesTest {

  private static final String SECRET = "synthetic-s3cr3t";

  @Test
  void everySettingOfSignInIsRequired() {
    assertThatThrownBy(() -> new SignInProperties(" ", SECRET, "https://app.example", null, "t"))
        .hasMessageContaining("owlmast.sign-in.client-id is required");
    assertThatThrownBy(() -> new SignInProperties("web", null, "https://app.example", null, "t"))
        .hasMessageContaining("owlmast.sign-in.client-secret is required");
    assertThatThrownBy(() -> new SignInProperties("web", SECRET, "", null, "t"))
        .hasMessageContaining("owlmast.sign-in.application-origin is required");
    assertThatThrownBy(() -> new SignInProperties("web", SECRET, "https://app.example", null, " "))
        .hasMessageContaining("owlmast.sign-in.tenant is required");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "https://app.example",
        "https://app.example:8443",
        "http://localhost:8080",
        "http://127.0.0.1:4174",
        "http://[::1]:8080"
      })
  void anHttpsOriginOrALoopbackHttpOriginIsAccepted(String origin) {
    SignInProperties properties = new SignInProperties("web", SECRET, origin, null, "default");
    assertThat(properties.applicationOrigin()).isEqualTo(origin);
    assertThat(properties.applicationUrl("/api/session/callback"))
        .isEqualTo(origin + "/api/session/callback");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "http://app.example",
        "http://localhost.example",
        "ftp://localhost",
        "https://app.example/",
        "https://app.example/shell",
        "https://app.example?x=1",
        "https://app.example#x",
        "https://user@app.example",
        "app.example",
        "https://",
        "not a url"
      })
  void anythingElseIsRefused(String origin) {
    assertThatThrownBy(() -> new SignInProperties("web", SECRET, origin, null, "default"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("owlmast.sign-in.application-origin")
        .hasMessageNotContaining(SECRET);
  }

  /** A Secret mounted or read as a file usually ends with a line end. */
  @Test
  void theSecretIsUsedWithoutSurroundingWhiteSpace() {
    assertThat(
            new SignInProperties("web", SECRET + "\n", "https://app.example", null, "default")
                .clientSecret())
        .isEqualTo(SECRET);
    assertThat(
            new SignInProperties("web", " " + SECRET + "\r\n", "https://app.example", null, "t")
                .clientSecret())
        .isEqualTo(SECRET);
  }

  @Test
  void theAudienceDefaultsToTheClientAndTheSecretIsNeverPrinted() {
    SignInProperties properties =
        new SignInProperties("web", SECRET, "https://app.example", " ", "default");
    assertThat(properties.audience()).isEqualTo("web");
    assertThat(
            new SignInProperties("web", SECRET, "https://app.example", "api", "default").audience())
        .isEqualTo("api");
    assertThat(properties.toString()).contains("web").doesNotContain(SECRET);
  }
}
