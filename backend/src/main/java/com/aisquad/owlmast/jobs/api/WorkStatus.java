package com.aisquad.owlmast.jobs.api;

/**
 * Lifecycle vocabulary of a work item (contract v1). {@code SUCCEEDED}, {@code FAILED}, {@code
 * DENIED} and {@code OUTCOME_UNCERTAIN} are terminal; the last awaits reconciliation (OM-16.05).
 */
public enum WorkStatus {
  /** Enqueued or scheduled for a retry; due when {@code next_attempt_at} has passed. */
  PENDING,
  /** Claimed under a lease; reclaimable once the lease expires. */
  RUNNING,
  /** Handler finished with an {@code APPLIED} effect outcome recorded. */
  SUCCEEDED,
  /** Attempts exhausted, or the lease expired after the last permitted attempt. */
  FAILED,
  /** The dispatch-time authorization recheck denied the handler; never invoked. */
  DENIED,
  /** The handler could not tell whether its external effect happened; awaiting reconciliation. */
  OUTCOME_UNCERTAIN;

  public boolean terminal() {
    return this != PENDING && this != RUNNING;
  }
}
