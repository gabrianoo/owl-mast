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

  /**
   * Failed, denied or unresolved attempt: object id as requested (possibly Unknown), no version.
   * The reason is normalised to what the envelope accepts on read ({@link #storableReason}), so a
   * row this module writes can always be read back.
   */
  public static AuditRecord unsuccessful(
      UUID eventId,
      AuditedMutation<?> mutation,
      AuditOutcome outcome,
      String safeReason,
      OffsetDateTime occurredAt) {
    if (!outcome.separateOutcomePath()) {
      throw new IllegalArgumentException(
          "only FAILED, DENIED or UNRESOLVED use the separate outcome path");
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
        Optional.of(storableReason(safeReason)),
        occurredAt,
        mutation.correlationId());
  }

  /** Stands in for a reason the diagnostics could not name (an anonymous exception class). */
  static final String REASON_UNKNOWN = "unknown-failure";

  /**
   * A reason the envelope accepts: non-blank, single-line and at most {@link
   * AuditEnvelopeContract#MAX_FIELD_LENGTH} characters. {@code SafeFailure} output is normally all
   * three; an anonymous class yields a blank name and a deep chain of long names can exceed the
   * bound, and such a row would commit but fail every later read of the object's history.
   */
  static String storableReason(String safeReason) {
    if (safeReason == null || safeReason.isBlank()) {
      return REASON_UNKNOWN;
    }
    String singleLine = safeReason.replace('\r', ' ').replace('\n', ' ').strip();
    if (singleLine.isEmpty()) {
      return REASON_UNKNOWN;
    }
    return singleLine.length() > AuditEnvelopeContract.MAX_FIELD_LENGTH
        ? singleLine.substring(0, AuditEnvelopeContract.MAX_FIELD_LENGTH)
        : singleLine;
  }
}
