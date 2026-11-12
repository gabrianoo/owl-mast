package com.aisquad.owlmast.platform.authorization;

import java.util.Objects;
import java.util.regex.Pattern;

/**
 * Raised when an authorization check denies an operation (AD-4). The reason is a short code from a
 * closed vocabulary chosen by the module that denied ({@code tenant-mismatch}, {@code
 * not-permitted}, ...), never a value from the request: it is safe to record in audit history and
 * to log. The access module (E02) raises it; audited mutations map it to the {@code DENIED}
 * outcome.
 */
public final class OperationDeniedException extends RuntimeException {

  private static final long serialVersionUID = 1L;
  private static final Pattern REASON_CODE = Pattern.compile("[a-z0-9]+(?:-[a-z0-9]+)*");

  private final String reasonCode;

  public OperationDeniedException(String reasonCode) {
    super("Operation denied: " + requireReasonCode(reasonCode));
    this.reasonCode = reasonCode;
  }

  /** Short kebab-case code, safe for audit rows and logs. */
  public String reasonCode() {
    return reasonCode;
  }

  private static String requireReasonCode(String reasonCode) {
    Objects.requireNonNull(reasonCode, "reasonCode");
    if (reasonCode.length() > 64 || !REASON_CODE.matcher(reasonCode).matches()) {
      throw new IllegalArgumentException(
          "denial reason must be a kebab-case code of at most 64 characters, never request data");
    }
    return reasonCode;
  }
}
