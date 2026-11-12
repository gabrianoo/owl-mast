package com.aisquad.owlmast.archfixtures.alpha.application;

import com.aisquad.owlmast.archfixtures.beta.api.BetaView;

/**
 * Fixture violation: alpha uses beta (through beta's api, which is allowed on its own) while beta
 * already uses alpha, so the two features form a dependency cycle.
 */
public final class AlphaLoop {

  public BetaView back() {
    return new BetaView("alpha");
  }
}
