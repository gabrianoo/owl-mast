package com.aisquad.owlmast.archfixtures.platform;

import com.aisquad.owlmast.archfixtures.alpha.application.AlphaService;

/** Fixture violation: platform depending on a feature. */
public final class LeakyPlatform {

  private final AlphaService alpha = new AlphaService();

  public String leak() {
    return alpha.name();
  }
}
