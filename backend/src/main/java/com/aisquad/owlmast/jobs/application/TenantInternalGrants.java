package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.WorkRegistration;
import com.aisquad.owlmast.jobs.api.WorkType;
import java.util.Objects;
import java.util.Set;

/**
 * The work types the jobs owner has granted the tenant-internal system-work privilege (AC7). A
 * handler's {@link WorkRegistration} only asks for the privilege; it holds it when its type is
 * listed here. Until OM-02.04 supplies the real authorization port, the fail-closed default
 * dispatches tenant-internal system work without a further check, so the privilege must not be
 * something a feature module can give itself.
 *
 * <p>The list is closed and owned by this module. It lives in {@code jobs.application}, which the
 * feature-module rules keep out of reach of every other feature, so a feature can neither extend it
 * nor replace the bean ({@code DurableWorkContractTest} states the rule by name). A new
 * tenant-internal work type is added here, in a change to the jobs module that is reviewed as a
 * change to the authorization boundary. Test fixtures, which are outside the production rules,
 * supply their own instance.
 */
public record TenantInternalGrants(Set<WorkType> types) {

  /**
   * The platform's own tenant-internal work: the audit publisher, which only copies the tenant's
   * committed audit intents into the tenant's audit history under the backend service identity. The
   * audit module owns the name ({@code AuditEnvelopeContract.PUBLISH_WORK_TYPE}); jobs cannot
   * import it without a module cycle, so the literal is repeated and a contract test compares the
   * two.
   */
  private static final TenantInternalGrants PLATFORM_DEFAULT =
      new TenantInternalGrants(Set.of(WorkType.of("audit.publish")));

  public TenantInternalGrants {
    types = Set.copyOf(Objects.requireNonNull(types, "types"));
  }

  public static TenantInternalGrants platformDefault() {
    return PLATFORM_DEFAULT;
  }

  public boolean contains(WorkType type) {
    return types.contains(type);
  }
}
