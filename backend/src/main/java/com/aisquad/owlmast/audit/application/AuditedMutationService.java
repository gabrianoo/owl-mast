package com.aisquad.owlmast.audit.application;

import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.audit.api.AuditOutcome;
import com.aisquad.owlmast.audit.api.AuditedMutation;
import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.audit.api.AuditedResult;
import com.aisquad.owlmast.audit.api.MutationOutcome;
import com.aisquad.owlmast.audit.domain.AuditRecord;
import com.aisquad.owlmast.audit.port.AuditStore;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.Scopes;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import lombok.extern.slf4j.Slf4j;
import reactor.core.publisher.Mono;

/**
 * Covered mutations (AD-6, AC3). Success: business change, {@code SUCCEEDED} intent and the {@code
 * audit.publish} work item commit together through the scoped transaction. Failure or denial: the
 * business transaction rolls back and the outcome record commits through a {@code REQUIRES_NEW}
 * scoped transaction that is independent of any transaction the caller may hold, so it survives the
 * rollback. Reasons are exception class chains only.
 */
@Slf4j
public final class AuditedMutationService implements AuditedMutations {

  private final ScopedTransactions transactions;
  private final ScopedTransactions separateTransactions;
  private final AuditStore store;
  private final WorkEnqueue enqueue;
  private final Clock clock;

  public AuditedMutationService(
      ScopedTransactions transactions,
      ScopedTransactions separateTransactions,
      AuditStore store,
      WorkEnqueue enqueue,
      Clock clock) {
    this.transactions = Objects.requireNonNull(transactions, "transactions");
    this.separateTransactions =
        Objects.requireNonNull(separateTransactions, "separateTransactions");
    this.store = Objects.requireNonNull(store, "store");
    this.enqueue = Objects.requireNonNull(enqueue, "enqueue");
    this.clock = Objects.requireNonNull(clock, "clock");
  }

  @Override
  public <T> Mono<AuditedResult<T>> execute(AuditedMutation<T> mutation) {
    Objects.requireNonNull(mutation, "mutation");
    return Scopes.current()
        .flatMap(scope -> {
          UUID eventId = UUID.randomUUID();
          OffsetDateTime occurredAt = OffsetDateTime.now(clock);
          return transactions
              .inTransaction(current -> commitWithIntent(mutation, eventId, occurredAt))
              .onErrorResume(error ->
                  recordUnsuccessful(mutation, eventId, occurredAt, error).then(Mono.error(error)));
        });
  }

  private <T> Mono<AuditedResult<T>> commitWithIntent(
      AuditedMutation<T> mutation, UUID eventId, OffsetDateTime occurredAt) {
    return Scopes.current()
        .flatMap(scope -> Mono.defer(() -> mutation.business().apply(scope)))
        .switchIfEmpty(Mono.error(MissingMutationOutcomeException::new))
        .flatMap(outcome -> recordSuccess(mutation, eventId, occurredAt, outcome));
  }

  private <T> Mono<AuditedResult<T>> recordSuccess(
      AuditedMutation<T> mutation,
      UUID eventId,
      OffsetDateTime occurredAt,
      MutationOutcome<T> outcome) {
    AuditRecord record = AuditRecord.succeeded(eventId, mutation, outcome, occurredAt);
    EnqueueRequest publish =
        EnqueueRequest.of(
            AuditEnvelopeContract.PUBLISH_WORK_TYPE,
            Map.of(AuditEnvelopeContract.PAYLOAD_EVENT_ID, eventId.toString()),
            mutation.correlationId());
    return store
        .recordIntent(record)
        .then(enqueue.enqueue(publish))
        .thenReturn(new AuditedResult<>(outcome.value(), eventId));
  }

  private Mono<Void> recordUnsuccessful(
      AuditedMutation<?> mutation, UUID eventId, OffsetDateTime occurredAt, Throwable error) {
    AuditOutcome outcome =
        error instanceof OperationDeniedException ? AuditOutcome.DENIED : AuditOutcome.FAILED;
    String reason =
        error instanceof OperationDeniedException denied
            ? denied.reasonCode()
            : SafeFailure.describe(error);
    AuditRecord record = AuditRecord.unsuccessful(eventId, mutation, outcome, reason, occurredAt);
    return separateTransactions
        .inTransaction(current -> store.recordOutcome(record))
        .doOnSuccess(ignored ->
            log.info(
                "Audited mutation {} on {} recorded as {} ({})",
                mutation.action(),
                mutation.objectType(),
                outcome,
                reason))
        .onErrorResume(secondary -> {
          log.error(
              "Audited mutation {} on {} failed ({}) and its {} record could not be written: {}",
              mutation.action(),
              mutation.objectType(),
              reason,
              outcome,
              SafeFailure.describe(secondary));
          return Mono.empty();
        });
  }

  /** A business function completed empty; only the class name is ever persisted. */
  static final class MissingMutationOutcomeException extends IllegalStateException {
    private static final long serialVersionUID = 1L;

    MissingMutationOutcomeException() {
      super("audited mutation completed without a MutationOutcome");
    }
  }
}
