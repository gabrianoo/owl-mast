package com.aisquad.owlmast.audit.api;

import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * Audit envelope, version 1 (OM-01.03-T1, AC3): what the audit history records about one operation.
 * There is no free-form payload field by design; {@code reason} is module-produced safe text (an
 * exception class chain or a fixed code), never request data. Empty {@code project} is the explicit
 * Unknown required until OM-02.02 supplies project identity; empty {@code objectId} or {@code
 * objectVersion} is Unknown for attempts that never produced an object.
 *
 * <p>Compatibility rule: within a version, new optional fields may be added and readers ignore
 * fields they do not know; removing, renaming or changing the meaning of a field requires a new
 * version. Every stored record carries the version it was written with and readers support every
 * version ever written.
 */
public record AuditEnvelope(
    int envelopeVersion,
    UUID eventId,
    AuditActor actor,
    TenantId tenant,
    Optional<String> project,
    String objectType,
    Optional<String> objectId,
    Optional<String> objectVersion,
    String action,
    AuditOutcome outcome,
    Optional<String> reason,
    OffsetDateTime occurredAt,
    OffsetDateTime recordedAt,
    String correlationId) {

  public AuditEnvelope {
    if (envelopeVersion < 1) {
      throw new IllegalArgumentException("envelope version must be positive");
    }
    Objects.requireNonNull(eventId, "eventId");
    Objects.requireNonNull(actor, "actor");
    Objects.requireNonNull(tenant, "tenant");
    Objects.requireNonNull(project, "project");
    AuditIdentifiers.requireIdentifier(objectType, "object type");
    Objects.requireNonNull(objectId, "objectId");
    Objects.requireNonNull(objectVersion, "objectVersion");
    AuditIdentifiers.requireIdentifier(action, "action");
    Objects.requireNonNull(outcome, "outcome");
    Objects.requireNonNull(reason, "reason");
    Objects.requireNonNull(occurredAt, "occurredAt");
    Objects.requireNonNull(recordedAt, "recordedAt");
    AuditIdentifiers.requireIdentifier(correlationId, "correlation id");
    project.ifPresent(value -> AuditIdentifiers.requireIdentifier(value, "project"));
    objectId.ifPresent(value -> AuditIdentifiers.requireIdentifier(value, "object id"));
    objectVersion.ifPresent(value -> AuditIdentifiers.requireIdentifier(value, "object version"));
    reason.ifPresent(value -> AuditIdentifiers.requireIdentifier(value, "reason"));
  }
}
