package com.aisquad.owlmast.audit.domain;

import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.audit.api.AuditOutcome;
import com.aisquad.owlmast.audit.api.AuditedMutation;
import com.aisquad.owlmast.audit.api.MutationOutcome;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * Envelope fields the module writes (the tenant comes from the bound transaction and the recorded
 * time from the database). Built from an {@link AuditedMutation} plus the outcome it reached.
 */
public record AuditRecord(
    int envelopeVersion,
    UUID eventId,
    AuditActor actor,
    Optional<String> project,
    String objectType,
    Optional<String> objectId,
    Optional<String> objectVersion,
    String action,
    AuditOutcome outcome,
    Optional<String> reason,
    OffsetDateTime occurredAt,
    String correlationId) {

  public AuditRecord {
    Objects.requireNonNull(eventId, "eventId");
    Objects.requireNonNull(actor, "actor");
    Objects.requireNonNull(project, "project");
    Objects.requireNonNull(objectType, "objectType");
    Objects.requireNonNull(objectId, "objectId");
    Objects.requireNonNull(objectVersion, "objectVersion");
    Objects.requireNonNull(action, "action");
    Objects.requireNonNull(outcome, "outcome");
    Objects.requireNonNull(reason, "reason");
    Objects.requireNonNull(occurredAt, "occurredAt");
    Objects.requireNonNull(correlationId, "correlationId");
  }

  public static <T> AuditRecord succeeded(
      UUID eventId,
      AuditedMutation<T> mutation,
      MutationOutcome<T> outcome,
      OffsetDateTime occurredAt) {
    return new AuditRecord(
        AuditEnvelopeContract.VERSION,
        eventId,
        mutation.actor(),
        mutation.project(),
        mutation.objectType(),
        Optional.of(outcome.objectId()),
        Optional.of(outcome.objectVersion()),
        mutation.action(),
        AuditOutcome.SUCCEEDED,
        Optional.empty(),
        occurredAt,
        mutation.correlationId());
  }

  /** Failed or denied attempt: object id as requested (possibly Unknown), no version. */
  public static AuditRecord unsuccessful(
      UUID eventId,
      AuditedMutation<?> mutation,
      AuditOutcome outcome,
      String safeReason,
      OffsetDateTime occurredAt) {
    if (!outcome.separateOutcomePath()) {
      throw new IllegalArgumentException("only FAILED or DENIED use the separate outcome path");
    }
    return new AuditRecord(
        AuditEnvelopeContract.VERSION,
        eventId,
        mutation.actor(),
        mutation.project(),
        mutation.objectType(),
        mutation.objectId(),
        Optional.empty(),
        mutation.action(),
        outcome,
        Optional.of(safeReason),
        occurredAt,
        mutation.correlationId());
  }
}
