package com.aisquad.owlmast.jobs.application;

import java.util.UUID;

/**
 * A completion or failure write was attempted with a lease that expired or was reclaimed (AC2). The
 * write changed nothing; raising it inside the handler transaction rolls the handler's database
 * effects back as well.
 */
public final class StaleLeaseException extends IllegalStateException {

  private static final long serialVersionUID = 1L;

  StaleLeaseException(UUID workItemId) {
    super(
        "Lease for work item "
            + workItemId
            + " is no longer current; the write was rejected and changed nothing");
  }
}
