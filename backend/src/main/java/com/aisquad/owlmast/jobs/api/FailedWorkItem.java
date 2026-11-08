package com.aisquad.owlmast.jobs.api;

import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * Operator view of a terminally failed, denied or outcome-uncertain item (AC5, FR-3, NFR-6). It
 * deliberately carries no payload; the reason is the safe class chain or a fixed reason code.
 */
public record FailedWorkItem(
    UUID id,
    TenantId tenant,
    WorkType type,
    WorkStatus status,
    int attemptCount,
    Optional<String> safeReason,
    OffsetDateTime finishedAt) {

  public FailedWorkItem {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(tenant, "tenant");
    Objects.requireNonNull(type, "type");
    Objects.requireNonNull(status, "status");
    Objects.requireNonNull(safeReason, "safeReason");
    Objects.requireNonNull(finishedAt, "finishedAt");
    if (!status.terminal() || status == WorkStatus.SUCCEEDED) {
      throw new IllegalArgumentException("a failed work item has a terminal non-success status");
    }
  }
}
