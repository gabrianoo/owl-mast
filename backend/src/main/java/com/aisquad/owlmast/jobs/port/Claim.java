package com.aisquad.owlmast.jobs.port;

import java.util.Objects;
import java.util.UUID;

/**
 * What one claimed row became: a decoded item under its new lease, or a row that could not be
 * decoded and was failed terminally under that lease.
 */
public sealed interface Claim permits ClaimedWork, Claim.Undecodable {

  /** A claimed row that could not become a {@code WorkItem}; it is already terminal. */
  record Undecodable(UUID id) implements Claim {

    public Undecodable {
      Objects.requireNonNull(id, "id");
    }
  }
}
