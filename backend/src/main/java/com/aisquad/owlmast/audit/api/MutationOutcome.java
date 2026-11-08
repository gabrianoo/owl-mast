package com.aisquad.owlmast.audit.api;

import java.util.Objects;

/**
 * What a covered mutation's business function reports when it succeeds: the caller's value plus the
 * identity and version of the object it changed, which complete the envelope.
 */
public record MutationOutcome<T>(T value, String objectId, String objectVersion) {

  public MutationOutcome {
    Objects.requireNonNull(value, "value");
    AuditIdentifiers.requireIdentifier(objectId, "object id");
    AuditIdentifiers.requireIdentifier(objectVersion, "object version");
  }
}
