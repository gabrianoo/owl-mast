package com.aisquad.owlmast.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.audit.api.AuditEnvelope;
import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.audit.api.AuditHistoryQuery;
import com.aisquad.owlmast.audit.api.AuditOutcome;
import com.aisquad.owlmast.audit.api.AuditedMutation;
import com.aisquad.owlmast.audit.api.AuditedResult;
import com.aisquad.owlmast.audit.api.MutationOutcome;
import com.aisquad.owlmast.audit.application.AuditedMutationService;
import com.aisquad.owlmast.audit.domain.AuditRecord;
import com.aisquad.owlmast.audit.port.AuditStore;
import com.aisquad.owlmast.fixtures.notes.DbProbe;
import com.aisquad.owlmast.fixtures.notes.DbProbe.AuditRow;
import com.aisquad.owlmast.fixtures.notes.DbProbe.WorkRow;
import com.aisquad.owlmast.fixtures.notes.NotesFixture;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.AuditedMode;
import com.aisquad.owlmast.fixtures.notes.NotesFixtureConfiguration;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.application.HandlerRegistry;
import com.aisquad.owlmast.jobs.application.TenantInternalGrants;
import com.aisquad.owlmast.jobs.application.TenantInternalOnlyDispatchAuthorization;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import io.r2dbc.spi.ConnectionFactory;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Import;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionSystemException;
import org.springframework.transaction.reactive.GenericReactiveTransaction;
import org.springframework.transaction.reactive.TransactionContext;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;
import reactor.util.context.ContextView;

/**
 * AC3, AC4 and AC8 against the pinned VectorChord PostgreSQL: the audit-publication intent commits
 * with the business row, failed and denied outcomes survive the rollback in a separate transaction,
 * a planted secret reaches no audit row, work record or log line, recovery after a fault before
 * publication is idempotent, and queries stay within the bound tenant.
 */
@SpringBootTest(
    properties = {
      "owlmast.jobs.scheduler.enabled=false",
      "owlmast.jobs.max-attempts=3",
      "owlmast.jobs.backoff-base=PT0.1S",
      "owlmast.jobs.backoff-cap=PT0.4S",
      "owlmast.jobs.lease-duration=PT5S",
      "owlmast.jobs.claim-batch-size=10"
    })
@Import({
  ContainersConfiguration.class,
  StubIdentityConfiguration.class,
  NotesFixtureConfiguration.class
})
@ExtendWith(OutputCaptureExtension.class)
class AuditedMutationIT {

  private static final ScopeContext TENANT_A = ScopeContext.of("tenant-a", "person-a");
  private static final ScopeContext TENANT_B = ScopeContext.of("tenant-b", "person-b");
  private static final AuditActor ACTOR = AuditActor.of(ActorKind.HUMAN, "person-a");
  private static final String SECRET = "s3cr3t-PLANTED-7b1d4e";

  @Autowired private NotesFixture notes;
  @Autowired private TenantInternalGrants grants;
  @Autowired private AuditHistoryQuery history;
  @Autowired private WorkProcessor processor;
  @Autowired private DbProbe db;
  @Autowired private ScopedTransactions transactions;
  @Autowired private ReactiveTransactionManager transactionManager;
  @Autowired private DatabaseClient databaseClient;
  @Autowired private AuditStore auditStore;
  @Autowired private WorkEnqueue enqueue;
  @Autowired private Clock clock;
  @Autowired private WorkRepository workRepository;
  @Autowired private HandlerRegistry registry;
  @Autowired private RetryPolicy policy;
  @Autowired private ConnectionFactory connectionFactory;

  @BeforeEach
  void reset() {
    notes.ensureTable().block();
    db.removeAuditEventFault();
    db.clearAll();
  }

  // --- AC3 ---------------------------------------------------------------------------------

  @Test
  void commitsTheIntentAndThePublishItemWithTheBusinessRowThenPublishesTheEnvelope() {
    AuditedResult<UUID> result = auditedCreate(TENANT_A, "hello", "corr-1", AuditedMode.SUCCEED);
    UUID noteId = result.value();
    UUID eventId = result.eventId();

    assertThat(notes.noteIds().block()).containsExactly(noteId);
    assertThat(db.intents())
        .singleElement()
        .satisfies(intent -> {
          assertThat(intent.eventId()).isEqualTo(eventId);
          assertThat(intent.tenant()).isEqualTo("tenant-a");
          assertThat(intent.outcome()).isEqualTo("SUCCEEDED");
          assertThat(intent.publishedAt()).isNull();
        });
    assertThat(db.workItems())
        .singleElement()
        .satisfies(work -> {
          assertThat(work.type()).isEqualTo(AuditEnvelopeContract.PUBLISH_WORK_TYPE.value());
          assertThat(work.payload()).contains(eventId.toString());
          assertThat(work.correlationId()).isEqualTo("corr-1");
          assertThat(work.enqueuedBy()).isEqualTo("person-a");
        });
    StepVerifier.create(find(TENANT_A, eventId)).verifyComplete();

    processor.runOnce().block();

    AuditEnvelope envelope = find(TENANT_A, eventId).block();
    assertThat(envelope.envelopeVersion()).isEqualTo(AuditEnvelopeContract.VERSION);
    assertThat(envelope.eventId()).isEqualTo(eventId);
    assertThat(envelope.actor()).isEqualTo(ACTOR);
    assertThat(envelope.tenant()).isEqualTo(TENANT_A.tenant());
    assertThat(envelope.project()).as("explicit Unknown until OM-02.02").isEmpty();
    assertThat(envelope.objectType()).isEqualTo(NotesFixture.OBJECT_TYPE);
    assertThat(envelope.objectId()).contains(noteId.toString());
    assertThat(envelope.objectVersion()).contains("1");
    assertThat(envelope.action()).isEqualTo(NotesFixture.CREATE_ACTION);
    assertThat(envelope.outcome()).isEqualTo(AuditOutcome.SUCCEEDED);
    assertThat(envelope.reason()).isEmpty();
    assertThat(envelope.occurredAt()).isNotNull();
    assertThat(envelope.recordedAt()).isAfterOrEqualTo(envelope.occurredAt().minusSeconds(5));
    assertThat(envelope.correlationId()).isEqualTo("corr-1");
    assertThat(unpublished(TENANT_A)).isZero();
    assertThat(db.workItems())
        .singleElement()
        .satisfies(work -> {
          assertThat(work.status()).isEqualTo("SUCCEEDED");
          assertThat(work.effectReference()).isEqualTo("audit.event:" + eventId);
        });
    assertThat(
            history
                .listByObject(NotesFixture.OBJECT_TYPE, noteId.toString(), 10)
                .contextWrite(Scopes.bind(TENANT_A))
                .collectList()
                .block())
        .singleElement()
        .isEqualTo(envelope);
  }

  @Test
  void aPlantedSecretReachesNoAuditRowWorkRecordOrLogLine(CapturedOutput output) {
    auditedCreate(TENANT_A, "note with " + SECRET, "corr-2", AuditedMode.SUCCEED);
    processor.runOnce().block();
    StepVerifier.create(
            notes
                .auditedCreate("again " + SECRET, ACTOR, "corr-3", AuditedMode.FAIL_AFTER_WRITE)
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectErrorSatisfies(error ->
            assertThat(error)
                .as("the secret really was in the failure")
                .hasMessageContaining(SECRET))
        .verify();

    assertThat(notes.bodies().block())
        .as("the business input holds it")
        .anyMatch(b -> b.contains(SECRET));
    assertThat(db.rowsAsText("audit.publication_intent")).noneMatch(row -> row.contains(SECRET));
    assertThat(db.rowsAsText("audit.event")).isNotEmpty().noneMatch(row -> row.contains(SECRET));
    assertThat(db.rowsAsText("jobs.work_item")).isNotEmpty().noneMatch(row -> row.contains(SECRET));
    assertThat(output.getAll()).doesNotContain(SECRET);
  }

  @Test
  void aFailedMutationRollsBackAndRecordsAFailedOutcomeInASeparateTransaction() {
    StepVerifier.create(
            notes
                .auditedCreate("doomed", ACTOR, "corr-4", AuditedMode.FAIL_AFTER_WRITE)
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(IllegalStateException.class)
        .verify();

    assertThat(notes.noteIds().block()).isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    List<AuditRow> events = db.auditEvents();
    assertThat(events)
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason()).isEqualTo("IllegalStateException");
          assertThat(event.objectId()).isNull();
          assertThat(event.objectVersion()).isNull();
          assertThat(event.actorKind()).isEqualTo("HUMAN");
          assertThat(event.actorId()).isEqualTo("person-a");
          assertThat(event.correlationId()).isEqualTo("corr-4");
        });
    AuditEnvelope envelope = find(TENANT_A, events.get(0).eventId()).block();
    assertThat(envelope.outcome()).isEqualTo(AuditOutcome.FAILED);
    assertThat(envelope.objectId()).isEmpty();
  }

  @Test
  void aDeniedOperationRecordsADeniedOutcomeWithItsReasonCodeAndNoBusinessRow() {
    StepVerifier.create(
            notes
                .auditedCreate("refused", ACTOR, "corr-5", AuditedMode.DENY)
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(OperationDeniedException.class)
        .verify();

    assertThat(notes.noteIds().block()).isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("DENIED");
          assertThat(event.reason()).isEqualTo("fixture-denied");
        });
  }

  @Test
  void theFailedOutcomeSurvivesTheRollbackOfAnEnclosingTransaction() {
    Mono<Void> flow =
        transactions
            .inTransaction(scope ->
                notes.auditedCreate("outer", ACTOR, "corr-6", AuditedMode.FAIL_AFTER_WRITE).then())
            .contextWrite(Scopes.bind(TENANT_A));

    StepVerifier.create(flow).expectError(IllegalStateException.class).verify();

    assertThat(notes.noteIds().block()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> assertThat(event.outcome()).isEqualTo("FAILED"));
  }

  @Test
  void anEnclosingRollbackAfterASuccessfulCallStillRecordsAFailedOutcome() {
    AtomicReference<UUID> eventId = new AtomicReference<>();
    Mono<Void> flow =
        transactions
            .inTransaction(scope ->
                notes
                    .auditedCreate("looked fine", ACTOR, "corr-6b", AuditedMode.SUCCEED)
                    .doOnNext(result -> eventId.set(result.eventId()))
                    .then(
                        Mono.<Void>error(new IllegalStateException("outer failure after success"))))
            .contextWrite(Scopes.bind(TENANT_A));

    StepVerifier.create(flow).expectError(IllegalStateException.class).verify();

    assertThat(eventId.get()).as("the audited call itself succeeded").isNotNull();
    assertThat(notes.noteIds().block()).isEmpty();
    assertThat(db.intents()).as("the success intent rolled back with the business row").isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.eventId()).isEqualTo(eventId.get());
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason()).isEqualTo("enclosing-transaction-rolled-back");
          assertThat(event.objectVersion()).isNull();
          assertThat(event.tenant()).isEqualTo("tenant-a");
        });
    assertThat(find(TENANT_A, eventId.get()).block().outcome()).isEqualTo(AuditOutcome.FAILED);
  }

  @Test
  void aCancellationAfterTheBusinessWriteStillRecordsAFailedOutcome() {
    CountDownLatch written = new CountDownLatch(1);
    Disposable subscription =
        notes
            .auditedCreateHanging("half done", ACTOR, "corr-6d", written::countDown)
            .contextWrite(Scopes.bind(TENANT_A))
            .subscribe(result -> {}, error -> {});

    assertThat(awaitLatch(written)).as("the business write completed").isTrue();
    subscription.dispose();

    await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> assertThat(db.auditEvents()).hasSize(1));
    assertThat(notes.noteIds().block()).as("the business write rolled back").isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason()).isEqualTo("execution-cancelled");
          assertThat(event.tenant()).isEqualTo("tenant-a");
          assertThat(event.correlationId()).isEqualTo("corr-6d");
        });
  }

  @Test
  void aCancellationDuringTheSeparateOutcomeWriteStillLeavesOneFailedOutcome() {
    CountDownLatch pending = new CountDownLatch(1);
    CountDownLatch cancelled = new CountDownLatch(1);
    OutcomeCountingStore hangingFirstOutcome =
        OutcomeCountingStore.hangingFirst(auditStore, pending, cancelled);
    NotesFixture viaHangingStore =
        new NotesFixture(databaseClient, transactions, enqueue, auditedOver(hangingFirstOutcome));
    Disposable subscription =
        transactions
            .inTransaction(scope ->
                viaHangingStore
                    .auditedCreate("cut short", ACTOR, "corr-6e", AuditedMode.FAIL_AFTER_WRITE)
                    .then())
            .contextWrite(Scopes.bind(TENANT_A))
            .subscribe(ignored -> {}, error -> {});

    assertThat(awaitLatch(pending))
        .as("the error path's outcome write is in flight, its insert not yet committed")
        .isTrue();
    subscription.dispose();
    assertThat(awaitLatch(cancelled)).as("the in-flight outcome write was cancelled").isTrue();

    await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> assertThat(db.auditEvents()).hasSize(1));
    assertThat(notes.noteIds().block()).as("the business write rolled back").isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason())
              .as("the observer's row, not the hung write's marked row, which rolled back")
              .isEqualTo("IllegalStateException")
              .isNotEqualTo(OutcomeCountingStore.HUNG_WRITE_MARKER);
          assertThat(event.tenant()).isEqualTo("tenant-a");
          assertThat(event.correlationId()).isEqualTo("corr-6e");
        });
    assertThat(hangingFirstOutcome.outcomeWrites())
        .as("the cancelled write plus the completion observer's committing write")
        .isEqualTo(2);
  }

  @Test
  void aFailedSeparateOutcomeWriteIsRecordedByTheCompletionObserver() {
    OutcomeCountingStore failingFirst = OutcomeCountingStore.failingFirst(auditStore);
    NotesFixture viaFailingStore =
        new NotesFixture(databaseClient, transactions, enqueue, auditedOver(failingFirst));

    StepVerifier.create(
            transactions
                .inTransaction(scope ->
                    viaFailingStore
                        .auditedCreate(
                            "write failed", ACTOR, "corr-6f", AuditedMode.FAIL_AFTER_WRITE)
                        .then())
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectErrorSatisfies(error ->
            assertThat(error)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("fixture failure with input"))
        .verify();

    assertThat(notes.noteIds().block()).as("the business write rolled back").isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason()).isEqualTo("IllegalStateException");
          assertThat(event.tenant()).isEqualTo("tenant-a");
          assertThat(event.correlationId()).isEqualTo("corr-6f");
        });
    assertThat(failingFirst.outcomeWrites())
        .as("the error path's failed write plus the completion observer's committing write")
        .isEqualTo(2);
  }

  @Test
  void aCommittedOutcomeStopsEveryLaterWriterForThatExecution() {
    OutcomeCountingStore plain = OutcomeCountingStore.counting(auditStore);
    StepVerifier.create(
            new NotesFixture(databaseClient, transactions, enqueue, auditedOver(plain))
                .auditedCreate("plain failure", ACTOR, "corr-6g", AuditedMode.FAIL_AFTER_WRITE)
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(IllegalStateException.class)
        .verify();
    assertThat(plain.outcomeWrites()).as("error path and observer, one write").isEqualTo(1);

    OutcomeCountingStore enclosed = OutcomeCountingStore.counting(auditStore);
    NotesFixture viaEnclosed =
        new NotesFixture(databaseClient, transactions, enqueue, auditedOver(enclosed));
    StepVerifier.create(
            transactions
                .inTransaction(scope ->
                    viaEnclosed
                        .auditedCreate("inner", ACTOR, "corr-6h", AuditedMode.FAIL_AFTER_WRITE)
                        .then())
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(IllegalStateException.class)
        .verify();
    assertThat(enclosed.outcomeWrites())
        .as("the enclosing rollback's observer skips the committed outcome")
        .isEqualTo(1);
    assertThat(db.auditEvents()).hasSize(2);
  }

  @Test
  void aRepeatedOutcomeWriteForOneEventIdKeepsTheFirstCommittedRow() {
    UUID eventId = UUID.randomUUID();
    AuditedMutation<UUID> mutation =
        AuditedMutation.<UUID>creating(
            ACTOR,
            NotesFixture.OBJECT_TYPE,
            NotesFixture.CREATE_ACTION,
            "corr-6f",
            scope -> Mono.empty());
    OffsetDateTime occurredAt = OffsetDateTime.now(clock);
    ScopedTransactions separate = separateTransactions();

    separate
        .inTransaction(scope ->
            auditStore.recordOutcome(
                AuditRecord.unsuccessful(
                    eventId, mutation, AuditOutcome.FAILED, "first-reason", occurredAt)))
        .contextWrite(Scopes.bind(TENANT_A))
        .block();
    StepVerifier.create(
            separate
                .inTransaction(scope ->
                    auditStore.recordOutcome(
                        AuditRecord.unsuccessful(
                            eventId, mutation, AuditOutcome.FAILED, "second-reason", occurredAt)))
                .contextWrite(Scopes.bind(TENANT_A)))
        .verifyComplete();

    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.eventId()).isEqualTo(eventId);
          assertThat(event.reason()).isEqualTo("first-reason");
        });
  }

  @Test
  void aCorrelationIdAtTheSharedBoundTravelsThroughIntentWorkItemAndHistory() {
    String atLimit = "c".repeat(WorkItemContract.MAX_CORRELATION_ID_LENGTH);
    UUID eventId = auditedCreate(TENANT_A, "bounded", atLimit, AuditedMode.SUCCEED).eventId();

    processor.runOnce().block();

    assertThat(db.workItems())
        .singleElement()
        .satisfies(work -> {
          assertThat(work.correlationId()).isEqualTo(atLimit);
          assertThat(work.status()).isEqualTo("SUCCEEDED");
        });
    assertThat(find(TENANT_A, eventId).block().correlationId()).isEqualTo(atLimit);
    assertThatThrownBy(
            () -> notes.auditedCreate("too long", ACTOR, atLimit + "x", AuditedMode.SUCCEED))
        .as("rejected while building the mutation, before any subscription or business work")
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("correlation id");
    assertThat(notes.noteIds().block()).hasSize(1);
    assertThat(db.auditEvents()).hasSize(1);
  }

  @Test
  void anEnclosingCommitAfterASuccessfulCallRecordsNothingExtra() {
    Mono<UUID> flow =
        transactions
            .inTransaction(scope ->
                notes
                    .auditedCreate("committed", ACTOR, "corr-6c", AuditedMode.SUCCEED)
                    .map(AuditedResult::eventId))
            .contextWrite(Scopes.bind(TENANT_A));

    UUID eventId = flow.block();
    processor.runOnce().block();

    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.eventId()).isEqualTo(eventId);
          assertThat(event.outcome()).isEqualTo("SUCCEEDED");
        });
    assertThat(unpublished(TENANT_A)).isZero();
  }

  @Test
  void executingWithoutAScopeFailsClosedBeforeAnyWrite() {
    StepVerifier.create(notes.auditedCreate("unscoped", ACTOR, "corr-7", AuditedMode.SUCCEED))
        .expectError(MissingScopeException.class)
        .verify();

    assertThat(notes.noteIds().block()).isEmpty();
    assertThat(db.auditEvents()).isEmpty();
    assertThat(db.intents()).isEmpty();
  }

  @Test
  void anEmptyBusinessResultRollsBackAndRecordsAFailedOutcome() {
    StepVerifier.create(
            notes
                .auditedCreate("empty", ACTOR, "corr-empty", AuditedMode.COMPLETE_EMPTY)
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectErrorMatches(
            error -> error.getClass().getSimpleName().equals("MissingMutationOutcomeException"))
        .verify();

    assertThat(notes.noteIds().block()).as("the business write rolled back").isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason()).isEqualTo("MissingMutationOutcomeException");
        });
  }

  @Test
  void anUnknownCommitOutcomeIsRecordedAsUnresolved() {
    StepVerifier.create(
            auditedOver(auditStore, UnknownCommitOutcome.ROLLED_BACK)
                .execute(notes.mutation("unknown", ACTOR, "corr-unknown", AuditedMode.SUCCEED))
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(TransactionSystemException.class)
        .verify();

    assertThat(notes.noteIds().block()).as("the commit never landed").isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("UNRESOLVED");
          assertThat(event.reason()).isEqualTo("transaction-completion-unknown");
          assertThat(event.correlationId()).isEqualTo("corr-unknown");
        });
  }

  @Test
  void aCommitThatLandedWithAnUnknownOutcomeIsPublishedAsSucceeded() {
    StepVerifier.create(
            auditedOver(auditStore, UnknownCommitOutcome.COMMITTED)
                .execute(notes.mutation("landed", ACTOR, "corr-landed", AuditedMode.SUCCEED))
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(TransactionSystemException.class)
        .verify();

    assertThat(notes.noteIds().block()).as("the commit landed").hasSize(1);
    UUID eventId = db.intents().get(0).eventId();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.eventId()).isEqualTo(eventId);
          assertThat(event.outcome()).isEqualTo("UNRESOLVED");
        });

    awaitPublishedAsSucceeded(eventId);

    assertThat(historyRows(eventId)).isEqualTo(1);
    AuditEnvelope published = find(TENANT_A, eventId).block();
    assertThat(published.outcome())
        .as("the intent proves the commit and replaces the unresolved record")
        .isEqualTo(AuditOutcome.SUCCEEDED);
    assertThat(published.reason()).isEmpty();
    assertThat(published.objectId()).isPresent();
    assertThat(
            db.count(
                "select count(*) from audit.event e join audit.publication_intent i using (event_id)"
                    + " where e.published_at >= i.recorded_at and e.recorded_at = i.recorded_at"))
        .as("the corrected row carries the intent's times and its own publication time")
        .isEqualTo(1);
    assertThat(unpublished(TENANT_A)).isZero();

    processor.runOnce().block();
    assertThat(find(TENANT_A, eventId).block().outcome()).isEqualTo(AuditOutcome.SUCCEEDED);
  }

  @Test
  void aLandedCommitRecordedAsFailedWhenTheUnresolvedWriteFailedIsCorrectedByPublication() {
    OutcomeCountingStore store = OutcomeCountingStore.failingFirst(auditStore);
    StepVerifier.create(
            auditedOver(store, UnknownCommitOutcome.COMMITTED)
                .execute(notes.mutation("landed", ACTOR, "corr-landed-2", AuditedMode.SUCCEED))
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(TransactionSystemException.class)
        .verify();

    assertThat(store.outcomeWrites()).as("observer failed, error path wrote").isEqualTo(2);
    UUID eventId = db.intents().get(0).eventId();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason()).isEqualTo("TransactionSystemException");
        });

    awaitPublishedAsSucceeded(eventId);

    assertThat(historyRows(eventId)).isEqualTo(1);
  }

  @Test
  void aRefusedCommitOfTheCallsOwnTransactionIsRecordedAsCommitRolledBack(CapturedOutput output) {
    StepVerifier.create(
            auditedOver(auditStore, UnknownCommitOutcome.REFUSED)
                .execute(notes.mutation("refused", ACTOR, "corr-refused", AuditedMode.SUCCEED))
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectErrorSatisfies(error ->
            assertThat(error)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("commit refused"))
        .verify();

    assertThat(notes.noteIds().block()).as("the refused commit rolled back").isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.reason())
              .as("no enclosing transaction exists; the call's own commit was refused")
              .isEqualTo("commit-rolled-back");
          assertThat(event.correlationId()).isEqualTo("corr-refused");
        });
    assertThat(output.getAll())
        .as("the refusing exception is still named in the log, next to the committed record")
        .contains("also ended as FAILED (IllegalStateException)")
        .doesNotContain("commit refused");
  }

  @Test
  void historyQueriesRejectBlankIdentifiersBeforeOpeningATransaction() {
    for (String[] arguments :
        new String[][] {
          {" ", "object-1"},
          {NotesFixture.OBJECT_TYPE, ""},
          {null, "object-1"},
          {NotesFixture.OBJECT_TYPE, "x".repeat(AuditEnvelopeContract.MAX_FIELD_LENGTH + 1)}
        }) {
      StepVerifier.create(
              history
                  .listByObject(arguments[0], arguments[1], 10)
                  .contextWrite(Scopes.bind(TENANT_A)))
          .expectErrorSatisfies(error ->
              assertThat(error)
                  .isInstanceOf(IllegalArgumentException.class)
                  .hasMessageContaining("object type and object id"))
          .verify();
    }
  }

  // --- AC4 ---------------------------------------------------------------------------------

  @Test
  void aPublishItemNamingAnotherTenantsIntentFailsTerminallyAndLeavesThatIntentAlone() {
    UUID eventA = auditedCreate(TENANT_A, "a", "corr-x1", AuditedMode.SUCCEED).eventId();
    UUID foreignItem =
        transactions
            .inTransaction(scope ->
                enqueue.enqueue(
                    EnqueueRequest.of(
                        AuditEnvelopeContract.PUBLISH_WORK_TYPE,
                        Map.of(AuditEnvelopeContract.PAYLOAD_EVENT_ID, eventA.toString()))))
            .contextWrite(Scopes.bind(TENANT_B))
            .block();

    assertThat(processor.processTenant(TENANT_B.tenant()).block()).isEqualTo(1L);

    WorkRow item = db.work(foreignItem);
    assertThat(item.status())
        .as("no retry can make another tenant's intent appear")
        .isEqualTo("FAILED");
    assertThat(item.attempts()).isEqualTo(1);
    assertThat(item.reason()).isEqualTo("MissingIntentException");
    assertThat(db.auditEvents()).as("tenant B copied nothing").isEmpty();
    assertThat(unpublished(TENANT_A)).isEqualTo(1);
    assertThat(db.intents())
        .singleElement()
        .satisfies(intent -> assertThat(intent.publishedAt()).isNull());

    processor.runOnce().block();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.eventId()).isEqualTo(eventA);
          assertThat(event.tenant()).isEqualTo("tenant-a");
        });
    assertThat(unpublished(TENANT_A)).isZero();
  }

  @Test
  void aPublishItemWithAMalformedOrMissingEventIdFailsTerminally() {
    UUID malformed =
        transactions
            .inTransaction(scope ->
                enqueue.enqueue(
                    EnqueueRequest.of(
                        AuditEnvelopeContract.PUBLISH_WORK_TYPE,
                        Map.of(AuditEnvelopeContract.PAYLOAD_EVENT_ID, "not-a-uuid"))))
            .contextWrite(Scopes.bind(TENANT_A))
            .block();
    UUID missing =
        transactions
            .inTransaction(scope ->
                enqueue.enqueue(
                    EnqueueRequest.of(AuditEnvelopeContract.PUBLISH_WORK_TYPE, Map.of())))
            .contextWrite(Scopes.bind(TENANT_A))
            .block();

    processor.runOnce().block();

    for (UUID itemId : List.of(malformed, missing)) {
      WorkRow item = db.work(itemId);
      assertThat(item.status()).isEqualTo("FAILED");
      assertThat(item.attempts()).isEqualTo(1);
      assertThat(item.reason()).startsWith("NonRetryableWorkException");
      assertThat(item.finishedAt()).isNotNull();
    }
    assertThat(db.auditEvents()).isEmpty();
  }

  @Test
  void aPublishItemKeepsRetryingPastTheConfiguredMaximumUntilTheIntentIsPublished(
      CapturedOutput output) {
    UUID eventId = auditedCreate(TENANT_A, "persistent", "corr-p", AuditedMode.SUCCEED).eventId();
    WorkRow item = db.workItems().get(0);
    assertThat(item.maxAttempts()).isEqualTo(WorkItemContract.UNLIMITED_ATTEMPTS);
    db.installAuditEventFault();

    WorkProcessor single = singleItemProcessor();
    int beyondTheConfiguredMaximum = policy.maxAttempts() + 1;
    await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          single.processTenant(TENANT_A.tenant()).block();
          assertThat(db.work(item.id()).attempts()).isEqualTo(beyondTheConfiguredMaximum);
        });
    assertThat(db.work(item.id()).status()).as("never abandoned").isEqualTo("PENDING");
    assertThat(historyRows(eventId)).isZero();
    assertThat(output.getAll())
        .as("an item past the configured attempts is surfaced to operators")
        .contains("reaching or passing the configured " + policy.maxAttempts());

    db.removeAuditEventFault();
    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          processor.runOnce().block();
          assertThat(historyRows(eventId)).isEqualTo(1);
        });
    assertThat(db.work(item.id()).status()).isEqualTo("SUCCEEDED");
    assertThat(unpublished(TENANT_A)).isZero();
  }

  @Test
  void aRequestCannotSetAnAttemptLimitOnAPublishItem() {
    EnqueueRequest limited =
        EnqueueRequest.of(
                AuditEnvelopeContract.PUBLISH_WORK_TYPE,
                Map.of(AuditEnvelopeContract.PAYLOAD_EVENT_ID, UUID.randomUUID().toString()))
            .withMaxAttempts(1);

    StepVerifier.create(
            transactions
                .inTransaction(scope -> enqueue.enqueue(limited))
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectErrorSatisfies(error ->
            assertThat(error)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("retried without an attempt limit"))
        .verify();
    assertThat(db.workItems())
        .as("the attempt limit of a publish item comes from its handler, never from a request")
        .isEmpty();
  }

  @Test
  void recoveryAfterAFaultBeforePublicationYieldsExactlyOneHistoryRecord() {
    UUID eventId = auditedCreate(TENANT_A, "faulted", "corr-8", AuditedMode.SUCCEED).eventId();
    db.installAuditEventFault();

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();
    WorkRow attempt = db.workItems().get(0);
    assertThat(attempt.status()).isEqualTo("PENDING");
    assertThat(attempt.attempts()).isEqualTo(1);
    assertThat(attempt.reason()).isNotBlank().doesNotContain("fixture:");
    assertThat(historyRows(eventId)).isZero();
    assertThat(unpublished(TENANT_A)).isEqualTo(1);

    db.removeAuditEventFault();
    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          processor.runOnce().block();
          assertThat(historyRows(eventId)).isEqualTo(1);
        });
    processor.runOnce().block();

    assertThat(historyRows(eventId)).isEqualTo(1);
    assertThat(unpublished(TENANT_A)).isZero();
    assertThat(db.workItems().get(0).status()).isEqualTo("SUCCEEDED");
    assertThat(find(TENANT_A, eventId).block().outcome()).isEqualTo(AuditOutcome.SUCCEEDED);
  }

  @Test
  void aRepeatPublicationLeavesTheSucceededHistoryRowUntouched() {
    UUID eventId = auditedCreate(TENANT_A, "repeat", "corr-r", AuditedMode.SUCCEED).eventId();
    processor.runOnce().block();
    assertThat(find(TENANT_A, eventId).block().outcome()).isEqualTo(AuditOutcome.SUCCEEDED);
    List<String> published = db.rowsAsText("audit.event");
    List<String> intent = db.rowsAsText("audit.publication_intent");

    Long written =
        transactions
            .inTransaction(scope -> auditStore.publish(eventId))
            .contextWrite(Scopes.bind(TENANT_A))
            .block();

    assertThat(written).as("a repeat inserts and upgrades nothing").isZero();
    assertThat(db.rowsAsText("audit.event"))
        .as("every column of the SUCCEEDED row, published_at included, is as first published")
        .containsExactlyInAnyOrderElementsOf(published);
    assertThat(db.rowsAsText("audit.publication_intent"))
        .containsExactlyInAnyOrderElementsOf(intent);
  }

  @Test
  void recoveryAfterAStopBeforePublicationRunsTwiceWithoutDuplicates() {
    List<UUID> eventIds =
        List.of(
            auditedCreate(TENANT_A, "one", "corr-9", AuditedMode.SUCCEED).eventId(),
            auditedCreate(TENANT_A, "two", "corr-10", AuditedMode.SUCCEED).eventId(),
            auditedCreate(TENANT_A, "three", "corr-11", AuditedMode.SUCCEED).eventId());
    assertThat(unpublished(TENANT_A)).as("the process stopped before publication").isEqualTo(3);

    processor.runOnce().block();
    processor.runOnce().block();

    eventIds.forEach(eventId -> assertThat(historyRows(eventId)).isEqualTo(1));
    assertThat(unpublished(TENANT_A)).isZero();
    assertThat(
            db.count(
                "select count(*) from audit.publication_intent i where not exists"
                    + " (select 1 from audit.event e where e.event_id = i.event_id)"))
        .as("no committed covered mutation lacks its audit record")
        .isZero();
  }

  // --- AC8 ---------------------------------------------------------------------------------

  @Test
  void publicationAndQueriesStayWithinTheBoundTenant() {
    UUID eventA = auditedCreate(TENANT_A, "a", "corr-12", AuditedMode.SUCCEED).eventId();
    AuditedResult<UUID> b = auditedCreate(TENANT_B, "b", "corr-13", AuditedMode.SUCCEED);

    processor.runOnce().block();

    assertThat(find(TENANT_A, eventA).block()).isNotNull();
    StepVerifier.create(find(TENANT_A, b.eventId())).verifyComplete();
    assertThat(find(TENANT_B, b.eventId()).block().tenant()).isEqualTo(TENANT_B.tenant());
    assertThat(
            history
                .listByObject(NotesFixture.OBJECT_TYPE, b.value().toString(), 10)
                .contextWrite(Scopes.bind(TENANT_A))
                .collectList()
                .block())
        .isEmpty();
    assertThat(db.workItems()).allSatisfy(work -> assertThat(work.status()).isEqualTo("SUCCEEDED"));

    auditedCreate(TENANT_B, "pending", "corr-14", AuditedMode.SUCCEED);
    assertThat(unpublished(TENANT_A)).isZero();
    assertThat(unpublished(TENANT_B)).isEqualTo(1);
  }

  @Test
  void theHistoryTableCarriesEveryDocumentedEnvelopeColumnAndNoPayload() {
    List<String> columns = db.columnsOf("audit", "event");

    assertThat(columns)
        .contains(
            "envelope_version",
            "event_id",
            "actor_kind",
            "actor_id",
            "tenant_id",
            "project_id",
            "object_type",
            "object_id",
            "object_version",
            "action",
            "outcome",
            "reason",
            "occurred_at",
            "recorded_at",
            "correlation_id")
        .noneMatch(column -> column.matches(".*(payload|details|data|body|content).*"));
  }

  @Test
  void theSeparateOutcomeWriteKeepsTheCallersContextButNotItsTransaction() {
    OutcomeProbeStore probe = new OutcomeProbeStore(auditStore, false);
    AtomicReference<TransactionContext> businessTransaction = new AtomicReference<>();
    AuditedMutation<UUID> failing =
        AuditedMutation.creating(
            ACTOR,
            NotesFixture.OBJECT_TYPE,
            NotesFixture.CREATE_ACTION,
            "corr-9a",
            scope ->
                Mono.deferContextual(context -> {
                  businessTransaction.set(context.get(TransactionContext.class));
                  return Mono.error(new IllegalStateException("fixture: business failure"));
                }));

    StepVerifier.create(
            auditedOver(probe)
                .execute(failing)
                .contextWrite(Scopes.bind(TENANT_A))
                .contextWrite(Context.of("probe-key", "probe-value")))
        .expectError(IllegalStateException.class)
        .verify();

    assertThat(probe.outcomeContexts())
        .as("at least one outcome write ran")
        .isNotEmpty()
        .allSatisfy(context -> {
          assertThat(context.<String>getOrEmpty("probe-key"))
              .as("keys that are not Spring's transaction keys travel with the outcome write")
              .contains("probe-value");
          assertThat(context.get(TransactionContext.class))
              .as("the write runs in its own transaction, not the one that is rolling back")
              .isNotSameAs(businessTransaction.get());
        });
    assertThat(businessTransaction.get()).isNotNull();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.correlationId()).isEqualTo("corr-9a");
        });
  }

  @Test
  void aStalledOutcomeWriteDoesNotHoldTheCallersErrorPastTheDeadline(CapturedOutput output) {
    OutcomeProbeStore neverAnswers = new OutcomeProbeStore(auditStore, true);
    AuditedMutationService bounded =
        new AuditedMutationService(
            transactions,
            separateTransactions(),
            neverAnswers,
            enqueue,
            clock,
            Duration.ofMillis(300));
    NotesFixture viaStalledStore = new NotesFixture(databaseClient, transactions, enqueue, bounded);

    Duration elapsed =
        StepVerifier.create(
                viaStalledStore
                    .auditedCreate("slow outcome", ACTOR, "corr-9b", AuditedMode.FAIL_AFTER_WRITE)
                    .contextWrite(Scopes.bind(TENANT_A)))
            .expectError(IllegalStateException.class)
            .verify(Duration.ofSeconds(10));

    assertThat(elapsed)
        .as("the observer's write and the error path's write each wait 300 ms at most")
        .isLessThan(Duration.ofSeconds(5));
    assertThat(neverAnswers.outcomeContexts()).as("both writers tried").hasSize(2);
    assertThat(notes.noteIds().block()).as("the business write rolled back").isEmpty();
    assertThat(db.auditEvents()).as("no outcome write committed").isEmpty();
    assertThat(output.getAll())
        .as("the lost record is named in the log")
        .contains("outcome record could not be written: TimeoutException")
        .contains("corr-9b");
    assertThatThrownBy(() ->
            new AuditedMutationService(
                transactions, separateTransactions(), auditStore, enqueue, clock, Duration.ZERO))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void anOutcomeNamingAnotherObjectThanRequestedRollsBackAndIsRecordedOnTheRequestedObject() {
    UUID noteId = UUID.randomUUID();
    AuditedMutation<UUID> renamed =
        AuditedMutation.changing(
            ACTOR,
            NotesFixture.OBJECT_TYPE,
            "note-requested",
            "note.update",
            "corr-9c",
            scope ->
                databaseClient
                    .sql(
                        "insert into "
                            + NotesFixture.TABLE
                            + " (id, tenant_id, body) values (:id, :tenant, 'changed')")
                    .bind("id", noteId)
                    .bind("tenant", scope.tenant().value())
                    .then()
                    .thenReturn(new MutationOutcome<>(noteId, "note-other", "2")));

    StepVerifier.create(
            auditedOver(auditStore).execute(renamed).contextWrite(Scopes.bind(TENANT_A)))
        .expectError(AuditRecord.OutcomeObjectMismatchException.class)
        .verify();

    assertThat(notes.noteIds().block()).as("the business change rolled back").isEmpty();
    assertThat(db.intents()).isEmpty();
    assertThat(db.workItems()).isEmpty();
    assertThat(db.auditEvents())
        .singleElement()
        .satisfies(event -> {
          assertThat(event.outcome()).isEqualTo("FAILED");
          assertThat(event.objectId()).isEqualTo("note-requested");
          assertThat(event.reason()).isEqualTo("OutcomeObjectMismatchException");
        });
    assertThat(
            history
                .listByObject(NotesFixture.OBJECT_TYPE, "note-other", 10)
                .contextWrite(Scopes.bind(TENANT_A))
                .collectList()
                .block())
        .as("the object nobody asked to change gains no history")
        .isEmpty();
  }

  // --- helpers -----------------------------------------------------------------------------

  /** The same wiring as {@code AuditConfiguration}, over the given store. */
  private AuditedMutationService auditedOver(AuditStore store) {
    return new AuditedMutationService(transactions, separateTransactions(), store, enqueue, clock);
  }

  /** The same wiring, but the business transaction's commit reports an unknown outcome. */
  private AuditedMutationService auditedOver(AuditStore store, UnknownCommitOutcome commit) {
    ScopedTransactions business =
        new ScopedTransactions(
            TransactionalOperator.create(
                new UnknownCommitOutcomeTransactionManager(connectionFactory, commit)),
            databaseClient);
    return new AuditedMutationService(business, separateTransactions(), store, enqueue, clock);
  }

  /**
   * What really happened to a commit that is then reported as failed: landed or rolled back with an
   * unknown outcome ({@code TransactionException}), or refused outright ({@code REFUSED}, a plain
   * runtime failure such as a deferred constraint, after which Spring rolls the transaction back).
   */
  private enum UnknownCommitOutcome {
    COMMITTED,
    ROLLED_BACK,
    REFUSED
  }

  /**
   * Commits or rolls back for real, then fails the commit with a {@code TransactionException}, so
   * Spring completes the transaction with {@code STATUS_UNKNOWN}, as when a connection drops while
   * the commit is in flight; or refuses the commit with a runtime failure, so Spring rolls back and
   * completes with {@code STATUS_ROLLED_BACK}.
   */
  private static final class UnknownCommitOutcomeTransactionManager
      extends R2dbcTransactionManager {
    private static final long serialVersionUID = 1L;
    private final UnknownCommitOutcome outcome;

    private UnknownCommitOutcomeTransactionManager(
        ConnectionFactory connectionFactory, UnknownCommitOutcome outcome) {
      super(connectionFactory);
      this.outcome = outcome;
    }

    @Override
    protected Mono<Void> doCommit(
        TransactionSynchronizationManager synchronizationManager,
        GenericReactiveTransaction status) {
      return switch (outcome) {
        case COMMITTED ->
            super.doCommit(synchronizationManager, status)
                .then(
                    Mono.error(new TransactionSystemException("fixture: commit outcome unknown")));
        case ROLLED_BACK ->
            doRollback(synchronizationManager, status)
                .then(
                    Mono.error(new TransactionSystemException("fixture: commit outcome unknown")));
        case REFUSED -> Mono.error(new IllegalStateException("fixture: commit refused"));
      };
    }
  }

  /** {@code REQUIRES_NEW} scoped transactions, as the separate outcome path uses. */
  private ScopedTransactions separateTransactions() {
    DefaultTransactionDefinition requiresNew = new DefaultTransactionDefinition();
    requiresNew.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    return new ScopedTransactions(
        TransactionalOperator.create(transactionManager, requiresNew), databaseClient);
  }

  /** Dispatches one item per run, so exactly one attempt never depends on the backoff. */
  private WorkProcessor singleItemProcessor() {
    return new WorkProcessor(
        transactions,
        workRepository,
        registry,
        new TenantInternalOnlyDispatchAuthorization(grants),
        new RetryPolicy(
            policy.maxAttempts(),
            policy.backoffBase(),
            policy.backoffCap(),
            policy.leaseDuration(),
            1),
        "single-item-processor");
  }

  private AuditedResult<UUID> auditedCreate(
      ScopeContext scope, String body, String correlationId, AuditedMode mode) {
    return notes
        .auditedCreate(body, ACTOR, correlationId, mode)
        .contextWrite(Scopes.bind(scope))
        .block();
  }

  private Mono<AuditEnvelope> find(ScopeContext scope, UUID eventId) {
    return history.find(eventId).contextWrite(Scopes.bind(scope));
  }

  private long unpublished(ScopeContext scope) {
    return history.countUnpublishedIntents().contextWrite(Scopes.bind(scope)).block();
  }

  private static boolean awaitLatch(CountDownLatch latch) {
    try {
      return latch.await(10, TimeUnit.SECONDS);
    } catch (InterruptedException interrupted) {
      Thread.currentThread().interrupt();
      return false;
    }
  }

  /** Drives the processor until the intent's history row reads {@code SUCCEEDED}. */
  private void awaitPublishedAsSucceeded(UUID eventId) {
    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          processor.runOnce().block();
          assertThat(find(TENANT_A, eventId).block().outcome())
              .as("the intent proves the commit and corrects the unsuccessful record")
              .isEqualTo(AuditOutcome.SUCCEEDED);
        });
  }

  private long historyRows(UUID eventId) {
    return db.count("select count(*) from audit.event where event_id = '" + eventId + "'");
  }

  /**
   * Captures the Reactor context every outcome write runs under; with {@code stalled} the write
   * never answers, as when the database stops responding after the statement was sent.
   */
  private static final class OutcomeProbeStore implements AuditStore {
    private final AuditStore delegate;
    private final boolean stalled;
    private final List<ContextView> outcomeContexts = new CopyOnWriteArrayList<>();

    private OutcomeProbeStore(AuditStore delegate, boolean stalled) {
      this.delegate = delegate;
      this.stalled = stalled;
    }

    List<ContextView> outcomeContexts() {
      return List.copyOf(outcomeContexts);
    }

    @Override
    public Mono<Void> recordIntent(AuditRecord record) {
      return delegate.recordIntent(record);
    }

    @Override
    public Mono<Long> publish(UUID eventId) {
      return delegate.publish(eventId);
    }

    @Override
    public Mono<Void> recordOutcome(AuditRecord record) {
      return Mono.deferContextual(context -> {
        outcomeContexts.add(context);
        return stalled ? Mono.<Void>never() : delegate.recordOutcome(record);
      });
    }

    @Override
    public Mono<AuditEnvelope> find(UUID eventId) {
      return delegate.find(eventId);
    }

    @Override
    public Flux<AuditEnvelope> listByObject(String objectType, String objectId, int limit) {
      return delegate.listByObject(objectType, objectId, limit);
    }

    @Override
    public Mono<Long> countUnpublishedIntents() {
      return delegate.countUnpublishedIntents();
    }
  }

  /**
   * Counts the outcome writes that reach the real store. {@link #hangingFirst}: the first outcome
   * write inserts a copy marked {@value #HUNG_WRITE_MARKER}, signals {@code pending} and never
   * completes (signalling {@code cancelled} when cancelled), so its transaction can only roll back.
   * {@link #failingFirst}: the first outcome write fails before reaching the database. Every later
   * call delegates unchanged.
   */
  private static final class OutcomeCountingStore implements AuditStore {
    static final String HUNG_WRITE_MARKER = "fixture-hung-outcome-write";

    private enum First {
      DELEGATE,
      HANG,
      FAIL
    }

    private final AuditStore delegate;
    private final AtomicReference<First> first;
    private final CountDownLatch pending;
    private final CountDownLatch cancelled;
    private final AtomicInteger outcomeWrites = new AtomicInteger();

    private OutcomeCountingStore(
        AuditStore delegate, First first, CountDownLatch pending, CountDownLatch cancelled) {
      this.delegate = delegate;
      this.first = new AtomicReference<>(first);
      this.pending = pending;
      this.cancelled = cancelled;
    }

    static OutcomeCountingStore counting(AuditStore delegate) {
      return new OutcomeCountingStore(
          delegate, First.DELEGATE, new CountDownLatch(0), new CountDownLatch(0));
    }

    static OutcomeCountingStore hangingFirst(
        AuditStore delegate, CountDownLatch pending, CountDownLatch cancelled) {
      return new OutcomeCountingStore(delegate, First.HANG, pending, cancelled);
    }

    static OutcomeCountingStore failingFirst(AuditStore delegate) {
      return new OutcomeCountingStore(
          delegate, First.FAIL, new CountDownLatch(0), new CountDownLatch(0));
    }

    int outcomeWrites() {
      return outcomeWrites.get();
    }

    @Override
    public Mono<Void> recordIntent(AuditRecord record) {
      return delegate.recordIntent(record);
    }

    @Override
    public Mono<Long> publish(UUID eventId) {
      return delegate.publish(eventId);
    }

    @Override
    public Mono<Void> recordOutcome(AuditRecord record) {
      return Mono.defer(() -> {
        outcomeWrites.incrementAndGet();
        return switch (first.getAndSet(First.DELEGATE)) {
          case DELEGATE -> delegate.recordOutcome(record);
          case FAIL -> Mono.<Void>error(new IllegalStateException("fixture: outcome write failed"));
          case HANG ->
              delegate
                  .recordOutcome(marked(record))
                  .then(Mono.fromRunnable(pending::countDown))
                  .then(Mono.<Void>never())
                  .doOnCancel(cancelled::countDown);
        };
      });
    }

    private static AuditRecord marked(AuditRecord record) {
      return new AuditRecord(
          record.envelopeVersion(),
          record.eventId(),
          record.actor(),
          record.project(),
          record.objectType(),
          record.objectId(),
          record.objectVersion(),
          record.action(),
          record.outcome(),
          Optional.of(HUNG_WRITE_MARKER),
          record.occurredAt(),
          record.correlationId());
    }

    @Override
    public Mono<AuditEnvelope> find(UUID eventId) {
      return delegate.find(eventId);
    }

    @Override
    public Flux<AuditEnvelope> listByObject(String objectType, String objectId, int limit) {
      return delegate.listByObject(objectType, objectId, limit);
    }

    @Override
    public Mono<Long> countUnpublishedIntents() {
      return delegate.countUnpublishedIntents();
    }
  }
}
