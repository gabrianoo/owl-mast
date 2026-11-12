package com.aisquad.owlmast.jobs.api;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;

/**
 * What a feature asks the jobs owner to run later. The tenant comes from the caller's bound scope,
 * never from the request. The payload holds identifiers only (bounded by {@link WorkItemContract});
 * the correlation id ties the item to the request or audit event that caused it. An absent {@code
 * maxAttempts} means the configured {@code owlmast.jobs.max-attempts}; a present one overrides it
 * for this item only (added in contract v1 with that absence-preserving meaning) and lies between 1
 * and {@link WorkItemContract#MAX_ATTEMPTS_PER_ITEM}, so no producer can enqueue work that never
 * runs out of attempts. A request that sets it for a work type whose handler registered without an
 * attempt limit ({@link WorkRegistration#unlimitedAttempts()}) is rejected at enqueue.
 */
public record EnqueueRequest(
    WorkType type,
    Map<String, String> payload,
    Optional<String> correlationId,
    OptionalInt maxAttempts) {

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
    Objects.requireNonNull(maxAttempts, "maxAttempts");
    maxAttempts.ifPresent(attempts -> {
      if (attempts < 1 || attempts > WorkItemContract.MAX_ATTEMPTS_PER_ITEM) {
        throw new IllegalArgumentException(
            "max attempts must be between 1 and " + WorkItemContract.MAX_ATTEMPTS_PER_ITEM);
      }
    });
  }

  public EnqueueRequest(
      WorkType type, Map<String, String> payload, Optional<String> correlationId) {
    this(type, payload, correlationId, OptionalInt.empty());
  }

  public static EnqueueRequest of(WorkType type, Map<String, String> payload) {
    return new EnqueueRequest(type, payload, Optional.empty());
  }

  public static EnqueueRequest of(
      WorkType type, Map<String, String> payload, String correlationId) {
    return new EnqueueRequest(type, payload, Optional.of(correlationId));
  }

  /**
   * The same request with a per-item attempt limit (1 to {@link
   * WorkItemContract#MAX_ATTEMPTS_PER_ITEM}) instead of the configured default.
   */
  public EnqueueRequest withMaxAttempts(int attempts) {
    return new EnqueueRequest(type, payload, correlationId, OptionalInt.of(attempts));
  }
}
