package com.aisquad.owlmast.compatibility.api;

import reactor.core.publisher.Mono;

/** Public operation: describe this backend's compatibility descriptor. */
public interface CompatibilityQuery {

  Mono<CompatibilityDescriptor> describe();
}
