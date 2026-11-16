package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;

class SignedInPersonTest {

  private static final String ISSUER = "https://id.example/realms/owl-mast";

  @Test
  void theDisplayNameIsTheNameThenTheUsernameThenAFixedText() {
    assertThat(person(Map.of("name", " Ada Synthetic ", "preferred_username", "ada")).displayName())
        .isEqualTo("Ada Synthetic");
    assertThat(person(Map.of("name", "  ", "preferred_username", "ada.synthetic")).displayName())
        .isEqualTo("ada.synthetic");
    assertThat(person(Map.of("preferred_username", "ada.synthetic")).displayName())
        .isEqualTo("ada.synthetic");
    // Never the email, the subject or the principal id.
    assertThat(person(Map.of("email", "ada@synthetic.invalid")).displayName())
        .isEqualTo(SignedInPerson.FALLBACK_DISPLAY_NAME);
  }

  @Test
  void anOverLongNameIsCutAndNeverInsideASurrogatePair() {
    int max = SignedInPerson.MAX_DISPLAY_NAME_LENGTH;
    assertThat(person(Map.of("name", "a".repeat(max))).displayName()).hasSize(max);
    assertThat(person(Map.of("name", "a".repeat(max + 50))).displayName())
        .isEqualTo("a".repeat(max));

    // U+1F989 (owl) is two chars; here its first half would be the last char kept.
    String owl = new String(Character.toChars(0x1F989));
    String cut = person(Map.of("name", "a".repeat(max - 1) + owl + "tail")).displayName();
    assertThat(cut).isEqualTo("a".repeat(max - 1));
    // Where the pair fits, it is kept whole.
    assertThat(person(Map.of("name", "a".repeat(max - 2) + owl + "tail")).displayName())
        .isEqualTo("a".repeat(max - 2) + owl);
  }

  @Test
  void identityAndProviderSessionComeFromTheTokenAsItIs() {
    SignedInPerson person = person(Map.of("sid", "provider-session", "name", "Ada"));
    assertThat(person.identity()).isEqualTo(new ExternalIdentity(ISSUER, "subject-1"));
    assertThat(person.providerSessionId()).contains("provider-session");
    assertThat(person(Map.of("sid", " ")).providerSessionId()).isEmpty();
    assertThat(person(Map.of()).providerSessionId()).isEmpty();
    assertThat(person.principalId()).isEqualTo(new PrincipalId("person:1"));
    assertThat(person.sessionRef()).isEqualTo("ref-1");
  }

  private static SignedInPerson person(Map<String, Object> extra) {
    Map<String, Object> claims = new HashMap<>(extra);
    claims.put("iss", ISSUER);
    claims.put("sub", "subject-1");
    Instant now = Instant.now();
    return new SignedInPerson(
        new OidcIdToken("synthetic", now, now.plusSeconds(300), claims),
        new PrincipalId("person:1"),
        "ref-1");
  }
}
