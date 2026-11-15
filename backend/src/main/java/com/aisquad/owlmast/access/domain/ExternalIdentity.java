package com.aisquad.owlmast.access.domain;

/**
 * What identifies a person to Owl Mast: the issuer that vouched for them and the subject it gave
 * them (OM-02.01). Nothing else is identity: display name, username and email can change or repeat
 * and are never compared or stored.
 *
 * <p>Both values are kept exactly as the validated credential carried them. They are bounded
 * because they are written to the principal table and come from a remote party.
 */
public record ExternalIdentity(String issuer, String subject) {

  public static final int MAX_ISSUER_LENGTH = 2048;
  public static final int MAX_SUBJECT_LENGTH = 255;

  public ExternalIdentity {
    requireBounded(issuer, "issuer", MAX_ISSUER_LENGTH);
    requireBounded(subject, "subject", MAX_SUBJECT_LENGTH);
  }

  private static void requireBounded(String value, String name, int max) {
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(name + " must not be blank");
    }
    if (value.length() > max) {
      throw new IllegalArgumentException(name + " must be at most " + max + " characters");
    }
  }
}
