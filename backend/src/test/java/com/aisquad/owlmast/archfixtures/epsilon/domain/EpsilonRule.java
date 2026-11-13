package com.aisquad.owlmast.archfixtures.epsilon.domain;

import com.aisquad.owlmast.archfixtures.epsilon.port.EpsilonPort;

/** Fixture violation: a domain rule that reaches a port. */
public final class EpsilonRule {

  public String apply(EpsilonPort port) {
    return port.load();
  }
}
