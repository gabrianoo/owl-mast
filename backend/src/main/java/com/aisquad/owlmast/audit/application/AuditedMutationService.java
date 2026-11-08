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
import java.util.concurrent.atomic.AtomicReference;
import lombok.extern.slf4j.Slf4j;
import org.springframework.transaction.reactive.TransactionSynchronization;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

/**
 * Covered mutations (AD-6, AC3). Success: business change, {@code SUCCEEDED} intent and the {@code
 * audit.publish} work item commit together through the scoped transaction. Anything else is
 * recorded as an outcome written through a {@code REQUIRES_NEW} scoped transaction that is
 * independent of the transaction being rolled back, so the evidence survives; the guarantee below
 * states exactly when that record exists.
 *
 * <p>The outcome is decided by a synchronization registered on the physical transaction
 * <em>before</em> the business function runs, so every way the transaction can end without
 * committing is observed: a business error or denial (recorded with the original exception class
 * chain or denial code), a cancelled subscription ({@value #REASON_CANCELLED}), a rollback of an
 * enclosing transaction after this call succeeded ({@value #REASON_ENCLOSING_ROLLBACK}), or an
 * unknown completion status ({@code UNRESOLVED}, {@value #REASON_COMPLETION_UNKNOWN}). The error
 * path records too, for transactions that end before the synchronization could run.
 *
 * <p>Guarantee: each execution leaves exactly one durable outcome row as long as one of these
 * writers commits, and never more than one. The per-execution guard records that an outcome has
 * <em>committed</em>, not that a writer started: it is set in the success signal of the {@code
 * REQUIRES_NEW} transaction, so a cancelled or failed outcome write leaves the completion observer
 * (or any later path) free to write it again. Writers may therefore overlap; {@link
 * AuditStore#recordOutcome} is idempotent on the event id, so the {@code audit.event} primary key
 * keeps it to one row even when a commit lands without its success signal.
 */
@Slf4j
public final class AuditedMutationService implements AuditedMutations {

  static final String REASON_ENCLOSING_ROLLBACK = "enclosing-transaction-rolled-back";
  static final String REASON_CANCELLED = "execution-cancelled";
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

  /** Observer first, business work second: no way of ending the transaction goes unseen. */
  private <T> Mono<AuditedResult<T>> commitWithIntent(Attempt<T> attempt) {
    return watchCompletion(attempt)
        .then(Scopes.current())
        .flatMap(scope -> Mono.defer(() -> attempt.mutation().business().apply(scope)))
        .switchIfEmpty(Mono.error(MissingMutationOutcomeException::new))
        .flatMap(outcome -> recordSuccess(attempt, outcome))
        .doOnError(attempt::failed)
        .doOnCancel(attempt::cancelled);
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
        .thenReturn(new AuditedResult<>(outcome.value(), attempt.eventId()));
  }

  /** Registers the completion observer on the physical transaction before any business work. */
  private Mono<Void> watchCompletion(Attempt<?> attempt) {
    return TransactionSynchronizationManager.forCurrentTransaction()
        .doOnNext(manager -> manager.registerSynchronization(new CompletionWatch(attempt)))
        .then();
  }

  /**
   * Writes the outcome detached from any transaction in the Reactor context, unless one has already
   * committed for this attempt. The attempt is marked recorded only after the separate transaction
   * commits; an idempotent insert absorbs overlapping writers.
   */
  private Mono<Void> recordOutcome(Attempt<?> attempt, AuditOutcome outcome, String reason) {
    return Mono.defer(
        () -> attempt.outcomeRecorded() ? Mono.empty() : writeOutcome(attempt, outcome, reason));
  }

  private Mono<Void> writeOutcome(Attempt<?> attempt, AuditOutcome outcome, String reason) {
    AuditedMutation<?> mutation = attempt.mutation();
    AuditRecord record =
        AuditRecord.unsuccessful(
            attempt.eventId(), mutation, outcome, reason, attempt.occurredAt());
    return separateTransactions
        .inTransaction(current -> store.recordOutcome(record))
        .doOnSuccess(ignored -> {
          attempt.markOutcomeRecorded();
          log.info(
              "Audited mutation {} on {} recorded as {} ({})",
              mutation.action(),
              mutation.objectType(),
              outcome,
              reason);
        })
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

  /**
   * One execution: identity, scope, start time, how it ended and whether an outcome record has
   * committed.
   */
  private static final class Attempt<T> {
    private final AuditedMutation<T> mutation;
    private final ScopeContext scope;
    private final OffsetDateTime occurredAt;
    private final UUID eventId = UUID.randomUUID();
    private final AtomicReference<Throwable> failure = new AtomicReference<>();
    private final AtomicBoolean cancelled = new AtomicBoolean();
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

    void failed(Throwable error) {
      failure.compareAndSet(null, error);
    }

    void cancelled() {
      cancelled.set(true);
    }

    boolean outcomeRecorded() {
      return outcomeRecorded.get();
    }

    /** Called only once the separate outcome transaction has committed. */
    void markOutcomeRecorded() {
      outcomeRecorded.set(true);
    }

    /** What a rollback means for this attempt: the original error or denial wins. */
    AuditOutcome rollbackOutcome() {
      Throwable error = failure.get();
      return error != null ? outcomeFor(error) : AuditOutcome.FAILED;
    }

    String rollbackReason() {
      Throwable error = failure.get();
      if (error != null) {
        return reasonFor(error);
      }
      return cancelled.get() ? REASON_CANCELLED : REASON_ENCLOSING_ROLLBACK;
    }
  }

  /** Records the outcome when the transaction carrying the attempt does not commit. */
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
            recordOutcome(attempt, attempt.rollbackOutcome(), attempt.rollbackReason());
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
