package com.aisquad.owlmast.archfixtures.epsilon.domain;

import com.aisquad.owlmast.archfixtures.alpha.api.AlphaView;

/** Fixture violation: a domain rule built on another feature, even through that feature's api. */
public final class ForeignRule {

  public String apply(AlphaView view) {
    return view.name();
  }
}
