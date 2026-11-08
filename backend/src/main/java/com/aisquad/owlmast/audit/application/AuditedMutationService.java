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
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import lombok.extern.slf4j.Slf4j;
import org.springframework.transaction.reactive.TransactionSynchronization;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

/**
 * Covered mutations (AD-6, AC3). Success: business change, {@code SUCCEEDED} intent and the {@code
 * audit.publish} work item commit together through the scoped transaction. Failure or denial: the
 * business transaction rolls back and the outcome record commits through a {@code REQUIRES_NEW}
 * scoped transaction that is independent of any transaction the caller may hold, so it survives the
 * rollback. Reasons are exception class chains or fixed codes only.
 *
 * <p>When the call joins an enclosing transaction and succeeds, the intent is only as durable as
 * that transaction. A synchronization registered on the physical transaction observes its
 * completion: a rollback after the successful call records a {@code FAILED} outcome with reason
 * {@value #REASON_ENCLOSING_ROLLBACK}; an unknown completion status records {@code UNRESOLVED}.
 * Both use the separate path, detached from the completed transaction, and each execution writes at
 * most one outcome record.
 */
@Slf4j
public final class AuditedMutationService implements AuditedMutations {

  static final String REASON_ENCLOSING_ROLLBACK = "enclosing-transaction-rolled-back";
  static final String REASON_COMPLETION_UNKNOWN = "transaction-completion-unknown";

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
          Attempt<T> attempt = new Attempt<>(mutation, scope, OffsetDateTime.now(clock));
          return transactions
              .inTransaction(current -> commitWithIntent(attempt))
              .onErrorResume(error ->
                  recordOutcome(attempt, outcomeFor(error), reasonFor(error))
                      .then(Mono.error(error)));
        });
  }

  private <T> Mono<AuditedResult<T>> commitWithIntent(Attempt<T> attempt) {
    return Scopes.current()
        .flatMap(scope -> Mono.defer(() -> attempt.mutation().business().apply(scope)))
        .switchIfEmpty(Mono.error(MissingMutationOutcomeException::new))
        .flatMap(outcome -> recordSuccess(attempt, outcome));
  }

  private <T> Mono<AuditedResult<T>> recordSuccess(Attempt<T> attempt, MutationOutcome<T> outcome) {
    AuditedMutation<T> mutation = attempt.mutation();
    AuditRecord record =
        AuditRecord.succeeded(attempt.eventId(), mutation, outcome, attempt.occurredAt());
    EnqueueRequest publish =
        EnqueueRequest.of(
            AuditEnvelopeContract.PUBLISH_WORK_TYPE,
            Map.of(AuditEnvelopeContract.PAYLOAD_EVENT_ID, attempt.eventId().toString()),
            mutation.correlationId());
    return store
        .recordIntent(record)
        .then(enqueue.enqueue(publish))
        .then(watchCompletion(attempt))
        .thenReturn(new AuditedResult<>(outcome.value(), attempt.eventId()));
  }

  /** Registers the completion observer on the physical transaction the intent was written in. */
  private Mono<Void> watchCompletion(Attempt<?> attempt) {
    return TransactionSynchronizationManager.forCurrentTransaction()
        .doOnNext(manager -> manager.registerSynchronization(new CompletionWatch(attempt)))
        .then();
  }

  /** Writes the outcome once per attempt, detached from any transaction in the Reactor context. */
  private Mono<Void> recordOutcome(Attempt<?> attempt, AuditOutcome outcome, String reason) {
    if (!attempt.claimOutcome()) {
      return Mono.empty();
    }
    AuditedMutation<?> mutation = attempt.mutation();
    AuditRecord record =
        AuditRecord.unsuccessful(
            attempt.eventId(), mutation, outcome, reason, attempt.occurredAt());
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
              "Audited mutation {} on {} ended as {} ({}) and its outcome record could not be"
                  + " written: {}",
              mutation.action(),
              mutation.objectType(),
              outcome,
              reason,
              SafeFailure.describe(secondary));
          return Mono.empty();
        })
        .contextWrite(Scopes.bind(attempt.scope()))
        .contextWrite(ctx -> Context.empty());
  }

  private static AuditOutcome outcomeFor(Throwable error) {
    return error instanceof OperationDeniedException ? AuditOutcome.DENIED : AuditOutcome.FAILED;
  }

  private static String reasonFor(Throwable error) {
    return error instanceof OperationDeniedException denied
        ? denied.reasonCode()
        : SafeFailure.describe(error);
  }

  /** One execution: its identity, scope, start time and whether an outcome was written. */
  private static final class Attempt<T> {
    private final AuditedMutation<T> mutation;
    private final ScopeContext scope;
    private final OffsetDateTime occurredAt;
    private final UUID eventId = UUID.randomUUID();
    private final AtomicBoolean outcomeRecorded = new AtomicBoolean();

    private Attempt(AuditedMutation<T> mutation, ScopeContext scope, OffsetDateTime occurredAt) {
      this.mutation = mutation;
      this.scope = scope;
      this.occurredAt = occurredAt;
    }

    AuditedMutation<T> mutation() {
      return mutation;
    }

    ScopeContext scope() {
      return scope;
    }

    OffsetDateTime occurredAt() {
      return occurredAt;
    }

    UUID eventId() {
      return eventId;
    }

    boolean claimOutcome() {
      return outcomeRecorded.compareAndSet(false, true);
    }
  }

  /** Records the outcome when the transaction carrying the intent does not commit. */
  private final class CompletionWatch implements TransactionSynchronization {
    private final Attempt<?> attempt;

    private CompletionWatch(Attempt<?> attempt) {
      this.attempt = attempt;
    }

    @Override
    public Mono<Void> afterCompletion(int status) {
      return switch (status) {
        case STATUS_COMMITTED -> Mono.empty();
        case STATUS_ROLLED_BACK ->
            recordOutcome(attempt, AuditOutcome.FAILED, REASON_ENCLOSING_ROLLBACK);
        default -> recordOutcome(attempt, AuditOutcome.UNRESOLVED, REASON_COMPLETION_UNKNOWN);
      };
    }
  }

  /** A business function completed empty; only the class name is ever persisted. */
  static final class MissingMutationOutcomeException extends IllegalStateException {
    private static final long serialVersionUID = 1L;

    MissingMutationOutcomeException() {
      super("audited mutation completed without a MutationOutcome");
    }
  }
}
