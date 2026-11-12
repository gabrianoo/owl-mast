package com.aisquad.owlmast.jobs.api;

import java.util.Objects;

/**
 * How a handler registers with the jobs owner. {@code tenantInternalSystemWork} declares that the
 * handler only changes the owning tenant's own records under the backend service identity and
 * performs no disclosure or external effect on anyone's behalf. Until OM-02.04 supplies the real
 * authorization recheck port, only such handlers are dispatched; every other handler is denied
 * (AC7, fail closed).
 *
 * <p>{@code unlimitedAttempts} declares that an item of this type never becomes terminal by running
 * out of attempts: a failed attempt is retried (with backoff up to the cap) whatever the configured
 * attempt limit, until the item succeeds or ends in another terminal way (the handler signals
 * {@link NonRetryableWorkException} or reports an uncertain effect, the recheck denies the
 * dispatch). The limit is stored on the item when it is enqueued, so it holds for items enqueued
 * while the handler registers this way. It exists for work that must not be abandoned, such as the
 * publication of a committed audit intent; it is the handler's decision for its own type, never a
 * producer's, and is allowed for tenant-internal system work only. Absent (the two-argument
 * constructor and the other factories) means the ordinary bounded limit.
 */
public record WorkRegistration(
    WorkType type, boolean tenantInternalSystemWork, boolean unlimitedAttempts) {

  public WorkRegistration {
    Objects.requireNonNull(type, "type");
    if (unlimitedAttempts && !tenantInternalSystemWork) {
      throw new IllegalArgumentException(
          "only tenant-internal system work may be retried without an attempt limit");
    }
  }

  public WorkRegistration(WorkType type, boolean tenantInternalSystemWork) {
    this(type, tenantInternalSystemWork, false);
  }

  public static WorkRegistration tenantInternal(WorkType type) {
    return new WorkRegistration(type, true);
  }

  /** Tenant-internal system work whose items are never abandoned after a number of attempts. */
  public static WorkRegistration tenantInternalRetriedWithoutLimit(WorkType type) {
    return new WorkRegistration(type, true, true);
  }

  public static WorkRegistration requiresAuthorization(WorkType type) {
    return new WorkRegistration(type, false);
  }
}
