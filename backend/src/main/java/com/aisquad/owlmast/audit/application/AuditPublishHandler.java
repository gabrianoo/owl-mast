package com.aisquad.owlmast.audit.application;

import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.audit.port.AuditStore;
import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import java.util.Objects;
import java.util.UUID;
import reactor.core.publisher.Mono;

/**
 * Idempotent publisher (AC4): copies the intent named by the work item into the audit history with
 * {@code ON CONFLICT DO NOTHING} and marks it published, inside the processor's scoped transaction
 * for the item's tenant. Repeating it after a crash or reclaim inserts nothing new. Registered as
 * tenant-internal system work: it only moves the tenant's own audit rows under the service
 * identity.
 */
public final class AuditPublishHandler implements WorkHandler {

  private static final WorkRegistration REGISTRATION =
      WorkRegistration.tenantInternal(AuditEnvelopeContract.PUBLISH_WORK_TYPE);

  private final AuditStore store;

  public AuditPublishHandler(AuditStore store) {
    this.store = Objects.requireNonNull(store, "store");
  }

  @Override
  public WorkRegistration registration() {
    return REGISTRATION;
  }

  @Override
  public Mono<EffectOutcome> handle(WorkItem item) {
    return Mono.fromCallable(() -> eventIdOf(item))
        .flatMap(store::publish)
        .map(inserted -> EffectOutcome.applied("audit.event:" + eventIdOf(item)));
  }

  private static UUID eventIdOf(WorkItem item) {
    String raw = item.payload().get(AuditEnvelopeContract.PAYLOAD_EVENT_ID);
    if (raw == null) {
      throw new IllegalArgumentException("audit.publish work item carries no event id");
    }
    return UUID.fromString(raw);
  }
}
