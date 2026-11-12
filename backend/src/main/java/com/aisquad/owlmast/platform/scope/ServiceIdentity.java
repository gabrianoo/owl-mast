package com.aisquad.owlmast.platform.scope;

import java.util.Objects;

/**
 * The backend's own execution identity (AD-3): the principal under which background processors
 * claim and run work on behalf of a tenant. It is distinct from every person and enrolled client
 * and never derived from a payload. Audit records produced under it carry actor kind {@code
 * SERVICE}.
 */
public final class ServiceIdentity {

  /** Principal of the single backend deployable (AD-2). */
  public static final PrincipalId BACKEND = new PrincipalId("service:owl-mast-backend");

  private ServiceIdentity() {}

  /** Scope a processor binds before touching one tenant's work or audit records. */
  public static ScopeContext backendScope(TenantId tenant) {
    return new ScopeContext(Objects.requireNonNull(tenant, "tenant"), BACKEND);
  }

  public static boolean isBackend(PrincipalId principal) {
    return BACKEND.equals(principal);
  }
}
