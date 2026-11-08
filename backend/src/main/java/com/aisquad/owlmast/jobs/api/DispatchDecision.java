package com.aisquad.owlmast.jobs.api;

/**
 * Result of the dispatch-time authorization recheck (AD-4, AD-6). Anything but ALLOW stops
 * dispatch.
 */
public enum DispatchDecision {
  ALLOW,
  /** The item becomes terminal {@code DENIED}; the handler is never invoked. */
  DENY,
  /** The port could not decide; the attempt is recorded as blocked and retried with backoff. */
  UNDECIDED
}
