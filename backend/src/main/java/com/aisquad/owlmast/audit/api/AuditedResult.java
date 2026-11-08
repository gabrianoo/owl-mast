package com.aisquad.owlmast.audit.api;

import java.util.Objects;
import java.util.UUID;

/** The caller's value together with the event id of the audit record that committed with it. */
public record AuditedResult<T>(T value, UUID eventId) {

  public AuditedResult {
    Objects.requireNonNull(value, "value");
    Objects.requireNonNull(eventId, "eventId");
  }
}
