package com.aisquad.owlmast.archfixtures.epsilon.port;

import com.aisquad.owlmast.archfixtures.epsilon.application.EpsilonService;

/** Fixture violation: a port that names the application service it serves. */
public interface EpsilonPort {

  String load();

  default String owner(EpsilonService service) {
    return service.name();
  }
}
