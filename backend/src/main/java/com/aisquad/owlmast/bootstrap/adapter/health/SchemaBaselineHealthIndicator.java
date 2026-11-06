package com.aisquad.owlmast.bootstrap.adapter.health;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import com.aisquad.owlmast.bootstrap.api.SchemaBaselineQuery;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.ReactiveHealthIndicator;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

/** Reports whether the bootstrap schema baseline (VectorChord plus pgvector) is in place. */
@Component("schemaBaseline")
@RequiredArgsConstructor
@Slf4j
class SchemaBaselineHealthIndicator implements ReactiveHealthIndicator {

  private final SchemaBaselineQuery query;

  @Override
  public Mono<Health> health() {
    return query
        .current()
        .map(SchemaBaselineHealthIndicator::up)
        .defaultIfEmpty(Health.down().withDetail("reason", "schema baseline not recorded").build())
        .onErrorResume(failure -> {
          // Diagnostic safety (NFR-6): log bounded class names only, never the message or cause
          // chain, because driver exceptions can carry connection details or payload fragments.
          log.warn("Schema baseline health check failed: {}", SafeFailure.describe(failure));
          return Mono.just(
              Health.down().withDetail("reason", "schema baseline query failed").build());
        });
  }

  private static Health up(SchemaBaseline baseline) {
    return Health.up()
        .withDetail("vchord", baseline.vchordVersion())
        .withDetail("vector", baseline.vectorVersion())
        .withDetail("appliedAt", baseline.appliedAt().toString())
        .build();
  }
}
