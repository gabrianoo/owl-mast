package com.aisquad.owlmast.access.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class ExternalIdentityTest {

  @Test
  void identityIsTheExactIssuerAndSubject() {
    ExternalIdentity identity = new ExternalIdentity("https://id.example/realms/x", "subject-1");
    assertThat(identity)
        .isEqualTo(new ExternalIdentity("https://id.example/realms/x", "subject-1"));
    // No normalisation: a trailing slash or another case is another identity.
    assertThat(identity)
        .isNotEqualTo(new ExternalIdentity("https://id.example/realms/x/", "subject-1"));
    assertThat(identity)
        .isNotEqualTo(new ExternalIdentity("https://id.example/realms/x", "Subject-1"));
  }

  @Test
  void bothPartsAreRequiredAndBounded() {
    assertThatThrownBy(() -> new ExternalIdentity(null, "s")).hasMessageContaining("issuer");
    assertThatThrownBy(() -> new ExternalIdentity(" ", "s")).hasMessageContaining("issuer");
    assertThatThrownBy(() -> new ExternalIdentity("i", "")).hasMessageContaining("subject");
    assertThatThrownBy(
            () -> new ExternalIdentity("i", "s".repeat(ExternalIdentity.MAX_SUBJECT_LENGTH + 1)))
        .hasMessageContaining("at most 255");
    assertThatThrownBy(
            () -> new ExternalIdentity("i".repeat(ExternalIdentity.MAX_ISSUER_LENGTH + 1), "s"))
        .hasMessageContaining("at most 2048");
  }

  @Test
  void everyEndOfASessionHasItsOwnAction() {
    assertThat(SessionEnd.values())
        .extracting(SessionEnd::action)
        .containsExactly("session.sign-out", "session.expire", "session.revoke", "session.replace");
  }
}
