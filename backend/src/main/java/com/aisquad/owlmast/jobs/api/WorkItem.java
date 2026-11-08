package com.aisquad.owlmast.jobs.api;

import com.aisquad.owlmast.platform.scope.TenantId;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * The view of a claimed work item handed to its {@link WorkHandler} (contract v1). The payload
 * holds identifiers only. {@link #idempotencyKey()} is derived from the item and therefore
 * identical on every attempt, so a handler can apply an external effect once across reclaims
 * (AD-6).
 */
public record WorkItem(
    UUID id,
    TenantId tenant,
    WorkType type,
    int contractVersion,
    Map<String, String> payload,
    int attempt,
    int maxAttempts,
    Optional<String> correlationId) {

  public WorkItem {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(tenant, "tenant");
    Objects.requireNonNull(type, "type");
    payload = Payloads.validated(payload);
    Objects.requireNonNull(correlationId, "correlationId");
    if (contractVersion < 1) {
      throw new IllegalArgumentException("contract version must be positive");
    }
    if (attempt < 1 || maxAttempts < 1) {
      throw new IllegalArgumentException("attempt and max attempts must be positive");
    }
  }

  /** Stable across attempts and reclaims: {@code owlmast-work:<item id>}. */
  public String idempotencyKey() {
    return "owlmast-work:" + id;
  }

  public boolean lastAttempt() {
    return attempt >= maxAttempts;
  }
}
