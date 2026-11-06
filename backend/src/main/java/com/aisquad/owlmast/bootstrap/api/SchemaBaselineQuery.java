package com.aisquad.owlmast.bootstrap.api;

import reactor.core.publisher.Mono;

/** Public read contract of the bootstrap feature. */
public interface SchemaBaselineQuery {

  /** The applied baseline, or empty when the bootstrap migration has not recorded one. */
  Mono<SchemaBaseline> current();
}
