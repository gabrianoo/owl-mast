package com.aisquad.owlmast.audit.api;

/**
 * Outcome vocabulary of an audited operation (envelope v1), aligned with OM-16.01's
 * requested/successful/failed/unresolved projection; {@code DENIED} is the separate safe outcome
 * AD-6 requires for refused attempts. Only {@code SUCCEEDED} may accompany a committed business
 * change.
 */
public enum AuditOutcome {
  /** An attempt was accepted for later processing; no business change is asserted. */
  REQUESTED,
  /** The business transaction committed; the record travels with it as a publication intent. */
  SUCCEEDED,
  /** The business transaction rolled back; recorded through the separate outcome path. */
  FAILED,
  /** Authorization refused the operation before any change; separate outcome path. */
  DENIED,
  /**
   * The result could not be determined (for example the enclosing transaction's completion status
   * was unknown); recorded through the separate outcome path and awaiting reconciliation.
   */
  UNRESOLVED;

  /** Outcomes written straight into the history, never as a publication intent. */
  public boolean separateOutcomePath() {
    return this == FAILED || this == DENIED || this == UNRESOLVED;
  }
}
