package com.aisquad.owlmast.access.adapter.web;

import lombok.AccessLevel;
import lombok.NoArgsConstructor;

/**
 * The session endpoints (docs/identity.md). They live below {@code /api} because that is the only
 * prefix the routing contract sends to the backend; the chart's realm import and an operator's
 * client registration name {@link #CALLBACK} and {@link #BACKCHANNEL_LOGOUT}.
 */
@NoArgsConstructor(access = AccessLevel.PRIVATE)
final class SessionPaths {

  /** What the shell reads: the signed-in person or the signed-out state. Public. */
  static final String SESSION = "/api/session";

  /** A browser navigation here starts sign-in at the identity provider. */
  static final String SIGN_IN = "/api/session/sign-in";

  /** Where the identity provider returns the browser with the authorization code. */
  static final String CALLBACK = "/api/session/callback";

  /** Ends the session here and at the identity provider. Needs the CSRF token. */
  static final String SIGN_OUT = "/api/session/sign-out";

  /** Where the identity provider announces that a session ended (OpenID Connect Back-Channel). */
  static final String BACKCHANNEL_LOGOUT = "/api/session/backchannel-logout";

  /** Query parameter on the shell's address that names why sign-in did not complete. */
  static final String OUTCOME_PARAMETER = "sign-in";

  static final String OUTCOME_FAILED = "failed";
  static final String OUTCOME_UNAVAILABLE = "unavailable";
}
