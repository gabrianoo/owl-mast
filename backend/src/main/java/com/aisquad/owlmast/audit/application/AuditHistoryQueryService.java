package com.aisquad.owlmast.audit.application;

import com.aisquad.owlmast.audit.api.AuditEnvelope;
import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.audit.api.AuditHistoryQuery;
import com.aisquad.owlmast.audit.port.AuditStore;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.util.Objects;
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/** Tenant-scoped reads over the audit-owned history; fail closed without a bound scope (AC8). */
public final class AuditHistoryQueryService implements AuditHistoryQuery {

  static final int MAX_LIMIT = 1000;

  private final ScopedTransactions transactions;
  private final AuditStore store;

  public AuditHistoryQueryService(ScopedTransactions transactions, AuditStore store) {
    this.transactions = Objects.requireNonNull(transactions, "transactions");
    this.store = Objects.requireNonNull(store, "store");
  }

  @Override
  public Mono<AuditEnvelope> find(UUID eventId) {
    Objects.requireNonNull(eventId, "eventId");
    return transactions.inTransaction(scope -> store.find(eventId));
  }

  @Override
  public Flux<AuditEnvelope> listByObject(String objectType, String objectId, int limit) {
    if (limit < 1 || limit > MAX_LIMIT) {
      return Flux.error(new IllegalArgumentException("limit must be between 1 and " + MAX_LIMIT));
    }
    if (!isIdentifier(objectType) || !isIdentifier(objectId)) {
      return Flux.error(
          new IllegalArgumentException(
              "object type and object id must be non-blank identifiers of at most "
                  + AuditEnvelopeContract.MAX_FIELD_LENGTH
                  + " characters"));
    }
    return transactions
        .inTransaction(scope -> store.listByObject(objectType, objectId, limit).collectList())
        .flatMapMany(Flux::fromIterable);
  }

  @Override
  public Mono<Long> countUnpublishedIntents() {
    return transactions.inTransaction(scope -> store.countUnpublishedIntents());
  }

  /** Checked before any transaction opens, so a bad argument fails clearly and cheaply. */
  private static boolean isIdentifier(String value) {
    return value != null
        && !value.isBlank()
        && value.length() <= AuditEnvelopeContract.MAX_FIELD_LENGTH;
  }
}
