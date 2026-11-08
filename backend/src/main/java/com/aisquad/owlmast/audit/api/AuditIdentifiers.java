package com.aisquad.owlmast.audit.api;

/** Envelope fields are bounded identifiers or codes, never content. */
final class AuditIdentifiers {

  static final int MAX_LENGTH = 256;

  private AuditIdentifiers() {}

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
