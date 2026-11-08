package com.aisquad.owlmast.audit.api;

import com.aisquad.owlmast.jobs.api.WorkItemContract;

/** Envelope fields are bounded identifiers or codes, never content. */
final class AuditIdentifiers {

  static final int MAX_LENGTH = 256;

  private AuditIdentifiers() {}

  /**
   * Correlation ids travel into the {@code audit.publish} work item, so they are validated up front
   * against both bounds; the two contracts share one limit and a test keeps them equal.
   */
  static void requireCorrelationId(String value) {
    requireIdentifier(value, "correlation id");
    if (value.length() > WorkItemContract.MAX_CORRELATION_ID_LENGTH) {
      throw new IllegalArgumentException(
          "correlation id must be at most "
              + WorkItemContract.MAX_CORRELATION_ID_LENGTH
              + " characters to be carried by the publish work item");
    }
  }

  static void requireIdentifier(String value, String name) {
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(name + " must not be blank");
    }
    if (value.length() > MAX_LENGTH) {
      throw new IllegalArgumentException(name + " must be at most " + MAX_LENGTH + " characters");
    }
    if (value.chars().anyMatch(c -> c == '\n' || c == '\r')) {
      throw new IllegalArgumentException(name + " must be a single line");
    }
  }
}
