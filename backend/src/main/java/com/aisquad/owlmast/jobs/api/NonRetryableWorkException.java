package com.aisquad.owlmast.jobs.api;

/**
 * A handler's signal that the attempt failed for a reason no retry can cure (a payload that cannot
 * name its subject, a referenced record that no longer exists). The processor records the item as
 * terminal {@code FAILED} on the current attempt, whatever its remaining attempt budget, so the
 * item appears in {@link FailedWorkQuery#listTerminalFailures(int)} instead of being retried at the
 * backoff cap for good. As with every failure, only the exception class chain is persisted; the
 * message is for logs and must not carry content or secrets.
 */
public class NonRetryableWorkException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  public NonRetryableWorkException(String message) {
    super(message);
  }

  public NonRetryableWorkException(String message, Throwable cause) {
    super(message, cause);
  }
}
