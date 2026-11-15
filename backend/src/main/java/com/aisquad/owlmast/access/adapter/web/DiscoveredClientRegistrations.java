package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.adapter.identity.IdentityDiscovery;
import com.aisquad.owlmast.access.adapter.identity.ProviderMetadata;
import com.aisquad.owlmast.access.adapter.identity.SignInProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;
import reactor.core.publisher.Mono;

/**
 * The one client registration of this installation, built from the issuer's discovery document when
 * it is needed (see {@link IdentityDiscovery}): the backend is a confidential client using the
 * authorization code grant with PKCE. The redirect address is the configured application origin,
 * never the request's own address, so forwarding headers have no say in it.
 */
@RequiredArgsConstructor
final class DiscoveredClientRegistrations implements ReactiveClientRegistrationRepository {

  static final String REGISTRATION_ID = "owl-mast";

  private final IdentityDiscovery discovery;
  private final SignInProperties properties;

  @Override
  public Mono<ClientRegistration> findByRegistrationId(String registrationId) {
    return REGISTRATION_ID.equals(registrationId)
        ? discovery.metadata().map(this::registration)
        : Mono.empty();
  }

  private ClientRegistration registration(ProviderMetadata metadata) {
    return ClientRegistration.withRegistrationId(REGISTRATION_ID)
        .clientId(properties.clientId())
        .clientSecret(properties.clientSecret())
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .clientSettings(ClientRegistration.ClientSettings.builder().requireProofKey(true).build())
        .redirectUri(properties.applicationUrl(SessionPaths.CALLBACK))
        .scope("openid", "profile", "email")
        .authorizationUri(metadata.authorizationEndpoint())
        .tokenUri(metadata.tokenEndpoint())
        .jwkSetUri(metadata.jwksUri())
        .issuerUri(metadata.issuer())
        .userNameAttributeName(IdTokenClaimNames.SUB)
        .clientName("Owl Mast")
        .build();
  }
}
