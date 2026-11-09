package com.aisquad.owlmast.jobs.api;

import java.time.Duration;

/**
 * Published constants of the durable work-item contract, version 1 (OM-01.03-T1). The prose
 * contract, vocabularies and compatibility rule live in {@code
 * docs/durable-work-and-audit-contract.md}; {@code DurableWorkContractTest} keeps both in step.
 *
 * <p>Compatibility rule: within a version, fields and payload keys may only be added, each with a
 * meaning that absent values preserve; removing, renaming or re-purposing one requires a new
 * version and the migration of in-flight items. Stored items carry the version they were enqueued
 * with.
 */
public final class WorkItemContract {

  /** Current work-item contract version written into every new item. */
  public static final int VERSION = 1;

  /**
   * Default attempts before an item becomes terminal {@code FAILED} ({@code
   * owlmast.jobs.max-attempts}).
   */
  public static final int DEFAULT_MAX_ATTEMPTS = 5;

  /** Default lease a claim holds before another processor may reclaim the item. */
  public static final Duration DEFAULT_LEASE_DURATION = Duration.ofSeconds(30);

  /** First retry delay; doubles per attempt up to {@link #DEFAULT_BACKOFF_CAP}. */
  public static final Duration DEFAULT_BACKOFF_BASE = Duration.ofSeconds(1);

  /** Upper bound of the retry delay. */
  public static final Duration DEFAULT_BACKOFF_CAP = Duration.ofMinutes(5);

  /** Items one claim takes per tenant per wake-up. */
  public static final int DEFAULT_CLAIM_BATCH_SIZE = 10;

  /** Delay between processor wake-ups by in-process Spring scheduling. */
  public static final Duration DEFAULT_POLL_INTERVAL = Duration.ofSeconds(1);

  /**
   * Delay before the first wake-up after start-up: none, so left-over work is recovered at once.
   */
  public static final Duration DEFAULT_INITIAL_DELAY = Duration.ZERO;

  /** Payloads carry identifiers, never content or secrets; these bounds keep them small. */
  public static final int MAX_PAYLOAD_ENTRIES = 32;

  public static final int MAX_PAYLOAD_KEY_LENGTH = 64;
  public static final int MAX_PAYLOAD_VALUE_LENGTH = 512;
  public static final int MAX_WORK_TYPE_LENGTH = 100;

  /**
   * Shared with the audit envelope: an audited mutation's correlation id becomes the publish
   * item's.
   */
  public static final int MAX_CORRELATION_ID_LENGTH = 256;

  public static final int MAX_EFFECT_REFERENCE_LENGTH = 256;

  private WorkItemContract() {}
}
