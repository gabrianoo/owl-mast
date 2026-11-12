package com.aisquad.owlmast.jobs.port;

import com.aisquad.owlmast.jobs.api.WorkItem;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

/** A work item together with the fencing token of the lease the claim obtained. */
public record ClaimedWork(WorkItem item, UUID leaseToken, OffsetDateTime leaseExpiresAt)
    implements Claim {

  public ClaimedWork {
    Objects.requireNonNull(item, "item");
    Objects.requireNonNull(leaseToken, "leaseToken");
    Objects.requireNonNull(leaseExpiresAt, "leaseExpiresAt");
  }
}
