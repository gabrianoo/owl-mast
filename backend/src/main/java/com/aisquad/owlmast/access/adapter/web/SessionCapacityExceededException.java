package com.aisquad.owlmast.access.adapter.web;

/**
 * The in-memory session store holds as many sessions as it may, so no sign-in can be started. It is
 * answered like an identity provider outage (503, or the shell's provider-error address): nothing
 * is wrong with the caller, and it passes when sessions expire.
 */
final class SessionCapacityExceededException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  SessionCapacityExceededException() {
    super("The session store is full");
  }
}
