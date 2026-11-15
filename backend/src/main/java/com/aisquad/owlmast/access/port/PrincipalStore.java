package com.aisquad.owlmast.access.port;

import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import reactor.core.publisher.Mono;

/**
 * The access module's principal records. Every operation runs inside a scoped transaction and acts
 * on the tenant bound to it, never on a tenant passed as a parameter.
 */
public interface PrincipalStore {

  /**
   * The principal bound to this identity in the transaction's tenant, created on first use. The
   * same issuer and subject always give the same principal.
   */
  Mono<PrincipalId> bind(ExternalIdentity identity);

  /**
   * Records a completed sign-in on the principal and returns how many it has had, or empty when the
   * transaction's tenant has no such principal.
   */
  Mono<Long> recordSignIn(PrincipalId principal);
}
