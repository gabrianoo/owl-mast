package com.aisquad.owlmast.access.domain;

/**
 * Why a browser session stopped existing, as the audit action that records it (OM-02.01). The codes
 * are a closed vocabulary of this module, never request data.
 */
public enum SessionEnd {
  /** The person signed out in the shell. */
  SIGNED_OUT("session.sign-out"),
  /**
   * The identity provider no longer renews the session (its lifetime passed, or it was ended there
   * and no logout notice arrived), or the backend dropped an idle session from memory.
   */
  EXPIRED("session.expire"),
  /** The identity provider announced the end of the session (back-channel logout). */
  REVOKED("session.revoke"),
  /** A later sign-in in the same browser session took its place. */
  REPLACED("session.replace");

  private final String action;

  SessionEnd(String action) {
    this.action = action;
  }

  public String action() {
    return action;
  }
}
