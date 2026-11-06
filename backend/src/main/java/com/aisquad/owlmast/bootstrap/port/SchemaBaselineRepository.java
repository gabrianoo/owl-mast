package com.aisquad.owlmast.bootstrap.port;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import reactor.core.publisher.Mono;

/** Consumer-owned persistence port; implemented by the feature's own adapter only. */
public interface SchemaBaselineRepository {

  Mono<SchemaBaseline> findBaseline();
}
