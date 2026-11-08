package com.aisquad.owlmast.jobs.api;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * What a feature asks the jobs owner to run later. The tenant comes from the caller's bound scope,
 * never from the request. The payload holds identifiers only (bounded by {@link WorkItemContract});
 * the correlation id ties the item to the request or audit event that caused it.
 */
public record EnqueueRequest(
    WorkType type, Map<String, String> payload, Optional<String> correlationId) {

  public EnqueueRequest {
    Objects.requireNonNull(type, "type");
    payload = Payloads.validated(payload);
    Objects.requireNonNull(correlationId, "correlationId");
    correlationId.ifPresent(id -> {
      if (id.isBlank() || id.length() > WorkItemContract.MAX_CORRELATION_ID_LENGTH) {
        throw new IllegalArgumentException(
            "correlation id must be non-blank and at most "
                + WorkItemContract.MAX_CORRELATION_ID_LENGTH
                + " characters");
      }
    });
  }

  public static EnqueueRequest of(WorkType type, Map<String, String> payload) {
    return new EnqueueRequest(type, payload, Optional.empty());
  }

  public static EnqueueRequest of(
      WorkType type, Map<String, String> payload, String correlationId) {
    return new EnqueueRequest(type, payload, Optional.of(correlationId));
  }
}
