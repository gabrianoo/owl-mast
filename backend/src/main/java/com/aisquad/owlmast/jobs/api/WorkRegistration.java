package com.aisquad.owlmast.jobs.api;

import java.util.Objects;

/**
 * How a handler registers with the jobs owner. {@code tenantInternalSystemWork} declares that the
 * handler only changes the owning tenant's own records under the backend service identity and
 * performs no disclosure or external effect on anyone's behalf. Until OM-02.04 supplies the real
 * authorization recheck port, only such handlers are dispatched; every other handler is denied
 * (AC7, fail closed).
 */
public record WorkRegistration(WorkType type, boolean tenantInternalSystemWork) {

  public WorkRegistration {
    Objects.requireNonNull(type, "type");
  }

  public static WorkRegistration tenantInternal(WorkType type) {
    return new WorkRegistration(type, true);
  }

  public static WorkRegistration requiresAuthorization(WorkType type) {
    return new WorkRegistration(type, false);
  }
}
