package com.aisquad.owlmast.audit.api;

import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * Internal read API over the audit-owned history (AC4, AC8). Requires a bound {@code ScopeContext};
 * only the bound tenant's records are visible. E16 builds the authorized, coverage-aware
 * projections on top of this; it is not an operator-facing endpoint.
 */
public interface AuditHistoryQuery {

  /** The published history record for the event id, if it exists in the bound tenant. */
  Mono<AuditEnvelope> find(UUID eventId);

  /** History of one object, newest first, bounded by {@code limit}. */
  Flux<AuditEnvelope> listByObject(String objectType, String objectId, int limit);

  /** Intents of the bound tenant not yet copied into the history; zero once recovery completes. */
  Mono<Long> countUnpublishedIntents();
}
