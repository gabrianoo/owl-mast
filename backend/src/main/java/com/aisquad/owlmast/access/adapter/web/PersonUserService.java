package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.application.SessionLedger;
import com.aisquad.owlmast.access.domain.ExternalIdentity;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import reactor.core.publisher.Mono;

/**
 * Turns a validated ID token into the signed-in person: binds the principal by issuer and subject
 * and records the sign-in. It runs inside the authentication step, after the token's signature,
 * issuer, audience and expiry were checked and before any session is authenticated, so a principal
 * that cannot be bound or a sign-in that cannot be recorded fails the sign-in instead of leaving a
 * session without them. The user-info endpoint is not called: the ID token carries all that is
 * used.
 */
@RequiredArgsConstructor
final class PersonUserService implements ReactiveOAuth2UserService<OidcUserRequest, OidcUser> {

  static final String UNUSABLE_IDENTITY = "invalid_id_token";

  private final SessionLedger ledger;

  @Override
  public Mono<OidcUser> loadUser(OidcUserRequest request) {
    ExternalIdentity identity;
    try {
      identity = SignedInPerson.identityOf(request.getIdToken());
    } catch (IllegalArgumentException unusable) {
      return Mono.error(new OAuth2AuthenticationException(new OAuth2Error(UNUSABLE_IDENTITY)));
    }
    String sessionRef = UUID.randomUUID().toString();
    return ledger
        .signedIn(identity, sessionRef)
        .<OidcUser>map(principal -> new SignedInPerson(request.getIdToken(), principal, sessionRef))
        .switchIfEmpty(
            Mono.error(() -> new AuthenticationServiceException("the principal was not bound")))
        .onErrorMap(
            failure -> !(failure instanceof AuthenticationException),
            failure -> new AuthenticationServiceException("the sign-in was not recorded", failure));
  }
}
