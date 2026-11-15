package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.adapter.web.SessionKeeper.Standing;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.util.List;
import java.util.Optional;
import lombok.AccessLevel;
import lombok.NoArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

/** The two filters this module adds to the security chain around authorization. */
@NoArgsConstructor(access = AccessLevel.PRIVATE)
final class SessionWebFilters {

  /**
   * Runs before authorization for a request that came with a signed-in session and asks {@link
   * SessionKeeper} whether the session still stands. A session that ended is removed from the
   * request, which then continues as an anonymous one: a protected operation answers 401, a public
   * one is still served. When the identity provider cannot be asked, the session is kept and the
   * request is answered 503, with two exceptions: where {@code servedWithoutSession} matches
   * (public content that does not depend on who asks) it continues without the session, and where
   * {@code endsSession} matches (sign-out) it continues with it, so a person can always end their
   * session here; the provider's part is then reported as unconfirmed.
   */
  static WebFilter standing(
      SessionKeeper sessions,
      SignInResponses responses,
      ServerWebExchangeMatcher servedWithoutSession,
      ServerWebExchangeMatcher endsSession) {
    return (ServerWebExchange exchange, WebFilterChain chain) ->
        sessions
            .sweep()
            .then(Mono.defer(ReactiveSecurityContextHolder::getContext))
            .map(SecurityContext::getAuthentication)
            .ofType(OAuth2AuthenticationToken.class)
            .flatMap(authentication ->
                exchange
                    .getSession()
                    .flatMap(session -> sessions.standing(exchange, session, authentication)))
            .defaultIfEmpty(Standing.CURRENT)
            .flatMap(standing ->
                switch (standing) {
                  case CURRENT -> chain.filter(exchange);
                  case ENDED -> withoutSession(exchange, chain);
                  case UNVERIFIABLE ->
                      endsSession
                          .matches(exchange)
                          .flatMap(ending ->
                              ending.isMatch()
                                  // Sign-out needs no verdict: the session ends here anyway.
                                  ? chain.filter(exchange)
                                  : servedWithoutSession
                                      .matches(exchange)
                                      .flatMap(match ->
                                          match.isMatch()
                                              ? withoutSession(exchange, chain)
                                              : responses.outage(exchange)));
                });
  }

  private static Mono<Void> withoutSession(ServerWebExchange exchange, WebFilterChain chain) {
    return chain.filter(exchange).contextWrite(ReactiveSecurityContextHolder.clearContext());
  }

  /**
   * Runs after authorization and binds the explicit {@link ScopeContext} of the authenticated
   * principal into the Reactor Context for everything the request does (AD-4, AD-5). The principal
   * is the one bound by issuer and subject; the tenant is the installation's until OM-02.02. A
   * request without an authenticated principal gets no scope, so code that needs one fails closed
   * with {@code MissingScopeException}.
   */
  static WebFilter scope(TenantId tenant) {
    return (ServerWebExchange exchange, WebFilterChain chain) ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication -> Mono.justOrEmpty(principalOf(authentication)))
            .map(Optional::of)
            .defaultIfEmpty(Optional.empty())
            .flatMap(principal ->
                principal
                    .map(bound ->
                        chain
                            .filter(exchange)
                            .contextWrite(Scopes.bind(new ScopeContext(tenant, bound))))
                    .orElseGet(() -> chain.filter(exchange)));
  }

  /** The principal an authentication of this chain was bound to, if it is one of ours. */
  static Optional<PrincipalId> principalOf(Authentication authentication) {
    if (authentication == null || !authentication.isAuthenticated()) {
      return Optional.empty();
    }
    if (authentication instanceof OAuth2AuthenticationToken session
        && session.getPrincipal() instanceof SignedInPerson person) {
      return Optional.of(person.principalId());
    }
    if (authentication instanceof BoundBearerAuthentication bearer) {
      return Optional.of(bearer.principalId());
    }
    return Optional.empty();
  }

  /** A validated bearer credential together with the principal it was bound to. */
  static final class BoundBearerAuthentication extends JwtAuthenticationToken {

    private static final long serialVersionUID = 1L;
    private final PrincipalId principalId;

    BoundBearerAuthentication(Jwt credential, PrincipalId principalId) {
      super(credential, List.of(), principalId.value());
      this.principalId = principalId;
    }

    PrincipalId principalId() {
      return principalId;
    }

    @Override
    public boolean equals(Object other) {
      return other instanceof BoundBearerAuthentication that
          && super.equals(other)
          && principalId.equals(that.principalId);
    }

    @Override
    public int hashCode() {
      return 31 * super.hashCode() + principalId.hashCode();
    }
  }
}
