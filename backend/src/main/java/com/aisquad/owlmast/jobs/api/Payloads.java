package com.aisquad.owlmast.jobs.api;

import java.util.Map;
import java.util.Objects;

/** Bounds on work payloads: small maps of identifiers, never content or secrets. */
final class Payloads {

  private Payloads() {}

  static Map<String, String> validated(Map<String, String> payload) {
    Objects.requireNonNull(payload, "payload");
    if (payload.size() > WorkItemContract.MAX_PAYLOAD_ENTRIES) {
      throw new IllegalArgumentException(
          "payload may hold at most " + WorkItemContract.MAX_PAYLOAD_ENTRIES + " entries");
    }
    payload.forEach(Payloads::requireEntry);
    return Map.copyOf(payload);
  }

  private static void requireEntry(String key, String value) {
    if (key == null || key.isBlank() || key.length() > WorkItemContract.MAX_PAYLOAD_KEY_LENGTH) {
      throw new IllegalArgumentException(
          "payload keys must be non-blank and at most "
              + WorkItemContract.MAX_PAYLOAD_KEY_LENGTH
              + " characters");
    }
    if (value == null || value.length() > WorkItemContract.MAX_PAYLOAD_VALUE_LENGTH) {
      throw new IllegalArgumentException(
          "payload values must be present and at most "
              + WorkItemContract.MAX_PAYLOAD_VALUE_LENGTH
              + " characters");
    }
  }
}
