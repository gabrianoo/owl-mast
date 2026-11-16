package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Stream;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;

/**
 * The person of a browser session: the validated ID token plus the principal it was bound to and a
 * reference that names the session in audit records. The reference is random and is not the session
 * id, which is the browser's credential.
 *
 * <p>The display name is shown and nothing else: it is never compared, stored or used as identity.
 */
final class SignedInPerson extends DefaultOidcUser {

  private static final long serialVersionUID = 1L;
  static final String FALLBACK_DISPLAY_NAME = "Signed-in person";
  static final int MAX_DISPLAY_NAME_LENGTH = 200;

  private final PrincipalId principalId;
  private final String sessionRef;

  SignedInPerson(OidcIdToken idToken, PrincipalId principalId, String sessionRef) {
    super(List.of(), idToken);
    this.principalId = Objects.requireNonNull(principalId, "principalId");
    this.sessionRef = Objects.requireNonNull(sessionRef, "sessionRef");
  }

  PrincipalId principalId() {
    return principalId;
  }

  String sessionRef() {
    return sessionRef;
  }

  ExternalIdentity identity() {
    return identityOf(getIdToken());
  }

  /** The issuer and subject exactly as the token carries them. */
  static ExternalIdentity identityOf(OidcIdToken idToken) {
    return new ExternalIdentity(idToken.getClaimAsString("iss"), idToken.getSubject());
  }

  /** The identity provider's id of its own session, when the token names one. */
  Optional<String> providerSessionId() {
    return Optional.ofNullable(getIdToken().getClaimAsString("sid")).filter(sid -> !sid.isBlank());
  }

  String displayName() {
    return Stream.of("name", "preferred_username")
        .map(claim -> getIdToken().getClaimAsString(claim))
        .filter(value -> value != null && !value.isBlank())
        .map(String::strip)
        .map(SignedInPerson::bounded)
        .findFirst()
        .orElse(FALLBACK_DISPLAY_NAME);
  }

  /** At most {@link #MAX_DISPLAY_NAME_LENGTH} characters, never ending inside a surrogate pair. */
  private static String bounded(String value) {
    if (value.length() <= MAX_DISPLAY_NAME_LENGTH) {
      return value;
    }
    int end =
        Character.isHighSurrogate(value.charAt(MAX_DISPLAY_NAME_LENGTH - 1))
            ? MAX_DISPLAY_NAME_LENGTH - 1
            : MAX_DISPLAY_NAME_LENGTH;
    return value.substring(0, end);
  }

  @Override
  public boolean equals(Object other) {
    return other instanceof SignedInPerson that
        && super.equals(other)
        && principalId.equals(that.principalId)
        && sessionRef.equals(that.sessionRef);
  }

  @Override
  public int hashCode() {
    return Objects.hash(super.hashCode(), principalId, sessionRef);
  }
}
