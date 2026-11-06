package com.aisquad.owlmast.archfixtures.beta.application;

import com.aisquad.owlmast.archfixtures.alpha.adapter.persistence.AlphaRepository;
import com.aisquad.owlmast.archfixtures.alpha.api.AlphaView;

/** Fixture violation: reaching into another feature's persistence adapter. */
public final class BetaService {

  private final AlphaRepository alphaRepository = new AlphaRepository();

  public AlphaView view() {
    return new AlphaView("rows=" + alphaRepository.rows());
  }
}
