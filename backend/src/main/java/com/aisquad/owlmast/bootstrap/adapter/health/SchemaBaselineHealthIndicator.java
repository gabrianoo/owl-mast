package com.aisquad.owlmast.bootstrap.adapter.health;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import com.aisquad.owlmast.bootstrap.api.SchemaBaselineQuery;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import java.util.concurrent.atomic.AtomicBoolean;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.ReactiveHealthIndicator;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

/**
 * Reports whether the bootstrap schema baseline (VectorChord plus pgvector) is in place on a
 * supported PostgreSQL server. An older server than {@link SchemaBaseline#MINIMUM_POSTGRESQL_MAJOR}
 * keeps readiness DOWN, so the instance takes no traffic; the durable-work scheduler checks the
 * same fact for itself and claims nothing on such a server.
 */
@Component("schemaBaseline")
@RequiredArgsConstructor
@Slf4j
class SchemaBaselineHealthIndicator implements ReactiveHealthIndicator {

  private final SchemaBaselineQuery query;
  private final AtomicBoolean unsupportedServerLogged = new AtomicBoolean();

  @Override
  public Mono<Health> health() {
    return query
        .current()
        .map(baseline -> baseline.serverIsSupported() ? up(baseline) : unsupportedServer(baseline))
        .defaultIfEmpty(Health.down().withDetail("reason", "schema baseline not recorded").build())
        .onErrorResume(failure -> {
          // Diagnostic safety (NFR-6): log bounded class names only, never the message or cause
          // chain, because driver exceptions can carry connection details or payload fragments.
          log.warn("Schema baseline health check failed: {}", SafeFailure.describe(failure));
          return Mono.just(
              Health.down().withDetail("reason", "schema baseline query failed").build());
        });
  }

  private Health unsupportedServer(SchemaBaseline baseline) {
    // Readiness is probed every few seconds: say it once per process, not once per probe.
    if (unsupportedServerLogged.compareAndSet(false, true)) {
      log.warn(
          "PostgreSQL {} answered; Owl Mast requires PostgreSQL {} or newer",
          baseline.postgresqlMajor(),
          SchemaBaseline.MINIMUM_POSTGRESQL_MAJOR);
    }
    return Health.down()
        .withDetail(
            "reason",
            "PostgreSQL " + SchemaBaseline.MINIMUM_POSTGRESQL_MAJOR + " or newer is required")
        .withDetail("postgresqlMajor", baseline.postgresqlMajor())
        .build();
  }

  private static Health up(SchemaBaseline baseline) {
    return Health.up()
        .withDetail("postgresqlMajor", baseline.postgresqlMajor())
        .withDetail("vchord", baseline.vchordVersion())
        .withDetail("vector", baseline.vectorVersion())
        .withDetail("appliedAt", baseline.appliedAt().toString())
        .build();
  }
}
