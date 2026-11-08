package com.aisquad.owlmast.audit.port;

import com.aisquad.owlmast.audit.api.AuditEnvelope;
import com.aisquad.owlmast.audit.domain.AuditRecord;
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * Persistence the audit owner needs. Every method runs inside a scoped transaction and filters on
 * the tenant bound to that transaction.
 */
public interface AuditStore {

  /** Writes a publication intent in the caller's (business) transaction. */
  Mono<Void> recordIntent(AuditRecord record);

  /**
   * Copies the intent into the history and marks it published. A repeat leaves the existing row; an
   * unsuccessful row for the same event (written when the commit's outcome was unknown although it
   * landed) is replaced by the intent, which proves the commit. Returns the number of history rows
   * inserted or upgraded: 1 the first time, 0 on a repeat. Errors when the intent does not exist
   * for the bound tenant.
   */
  Mono<Long> publish(UUID eventId);

  /**
   * Writes a failed, denied or unresolved outcome straight into the history (separate outcome
   * path). Idempotent on the event id ({@code ON CONFLICT DO NOTHING}): overlapping writers for one
   * execution leave exactly one history row, the first to commit.
   */
  Mono<Void> recordOutcome(AuditRecord record);

  Mono<AuditEnvelope> find(UUID eventId);

  Flux<AuditEnvelope> listByObject(String objectType, String objectId, int limit);

  Mono<Long> countUnpublishedIntents();
}
