package com.aisquad.owlmast.platform.scope;

import java.util.Objects;

/**
 * Explicit authorization scope carried in the Reactor {@code Context} across every asynchronous
 * boundary (AD-4, AD-5). The access module (E02) extends it with project/source/purpose scope; it
 * is never derived from a ThreadLocal.
 */
public record ScopeContext(TenantId tenant, PrincipalId principal) {

  public ScopeContext {
    Objects.requireNonNull(tenant, "tenant");
    Objects.requireNonNull(principal, "principal");
  }

  public static ScopeContext of(String tenant, String principal) {
    return new ScopeContext(new TenantId(tenant), new PrincipalId(principal));
  }
}
