package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.DispatchAuthorization;
import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import java.util.Objects;
import reactor.core.publisher.Mono;

/**
 * Fail-closed default recheck used until OM-02.04 supplies the access module's port (AC7): only
 * tenant-internal system work may run; everything else is denied. A registration that says
 * tenant-internal is not enough: the item's type must also hold the privilege in the jobs owner's
 * {@link TenantInternalGrants}. {@link HandlerRegistry} already refuses such a registration at
 * startup; checking again here means the decision at dispatch does not rest on how the registry
 * that feeds this recheck was built.
 */
public final class TenantInternalOnlyDispatchAuthorization implements DispatchAuthorization {

  private final TenantInternalGrants grants;

  public TenantInternalOnlyDispatchAuthorization(TenantInternalGrants grants) {
    this.grants = Objects.requireNonNull(grants, "grants");
  }

  @Override
  public Mono<DispatchDecision> recheck(WorkItem item, WorkRegistration registration) {
    boolean granted =
        registration.tenantInternalSystemWork()
            && grants.contains(registration.type())
            && registration.type().equals(item.type());
    return Mono.just(granted ? DispatchDecision.ALLOW : DispatchDecision.DENY);
  }
}
