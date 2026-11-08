package com.aisquad.owlmast.compatibility.adapter.web;

import com.aisquad.owlmast.compatibility.api.CompatibilityDescriptor;
import com.aisquad.owlmast.compatibility.api.CompatibilityQuery;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

/**
 * {@code GET /api/compatibility}: the public descriptor an independently deployed frontend reads
 * before showing protected features, and the pre-rollout check queries against a live backend. It
 * carries no protected content and needs no scope.
 */
@RestController
class CompatibilityController {

  static final String PATH = "/api/compatibility";

  private final CompatibilityQuery query;

  CompatibilityController(CompatibilityQuery query) {
    this.query = query;
  }

  @GetMapping(path = PATH, produces = MediaType.APPLICATION_JSON_VALUE)
  Mono<CompatibilityDescriptor> describe() {
    return query.describe();
  }
}
