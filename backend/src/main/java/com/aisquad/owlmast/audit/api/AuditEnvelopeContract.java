package com.aisquad.owlmast.audit.api;

import com.aisquad.owlmast.jobs.api.WorkType;

/**
 * Published constants of the audit-envelope contract, version 1 (OM-01.03-T1). The prose contract
 * lives in {@code docs/durable-work-and-audit-contract.md}; {@code DurableWorkContractTest} keeps
 * the document, {@link AuditEnvelope} and the vocabularies in step.
 */
public final class AuditEnvelopeContract {

  /** Current envelope version written into every new intent and history record. */
  public static final int VERSION = 1;

  /** Work type of the idempotent publisher that moves intents into the history. */
  public static final WorkType PUBLISH_WORK_TYPE = new WorkType("audit.publish");

  /** Payload key of the publish work item carrying the event id. */
  public static final String PAYLOAD_EVENT_ID = "eventId";

  /**
   * Upper bound of every textual envelope field (identifiers, codes, the safe reason): single-line
   * text of at most this many characters.
   */
  public static final int MAX_FIELD_LENGTH = 256;

  /**
   * Attempt limit of every publish work item: effectively unbounded, so a committed mutation's
   * intent is retried (at most every {@code owlmast.jobs.backoff-cap}) until it reaches the history
   * instead of being abandoned after {@code owlmast.jobs.max-attempts} (AC4).
   */
  public static final int PUBLISH_MAX_ATTEMPTS = Integer.MAX_VALUE;

  private AuditEnvelopeContract() {}
}
