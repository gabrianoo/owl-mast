package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.DispatchAuthorization;
import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import reactor.core.publisher.Mono;

/**
 * Fail-closed default recheck used until OM-02.04 supplies the access module's port (AC7): only
 * handlers registered as tenant-internal system work may run; everything else is denied.
 */
public final class TenantInternalOnlyDispatchAuthorization implements DispatchAuthorization {

  @Override
  public Mono<DispatchDecision> recheck(WorkItem item, WorkRegistration registration) {
    return Mono.just(
        registration.tenantInternalSystemWork() ? DispatchDecision.ALLOW : DispatchDecision.DENY);
  }
}
