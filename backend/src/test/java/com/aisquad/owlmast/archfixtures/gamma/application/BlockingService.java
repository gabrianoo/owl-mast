package com.aisquad.owlmast.archfixtures.gamma.application;

import reactor.core.publisher.Mono;

/** Fixture violation: blocking on a publisher inside application code. */
public final class BlockingService {

  public String value() {
    return Mono.just("gamma").block();
  }
}
