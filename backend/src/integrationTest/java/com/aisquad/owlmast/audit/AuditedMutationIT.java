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
import com.aisquad.owlmast.audit.api.AuditedResult;
import com.aisquad.owlmast.fixtures.notes.DbProbe;
import com.aisquad.owlmast.fixtures.notes.DbProbe.AuditRow;
import com.aisquad.owlmast.fixtures.notes.DbProbe.WorkRow;
import com.aisquad.owlmast.fixtures.notes.NotesFixture;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.AuditedMode;
import com.aisquad.owlmast.fixtures.notes.NotesFixtureConfiguration;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Import;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

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
  @Autowired private AuditHistoryQuery history;
  @Autowired private WorkProcessor processor;
  @Autowired private DbProbe db;
  @Autowired private ScopedTransactions transactions;

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

  // --- AC4 ---------------------------------------------------------------------------------

  @Test
  void recoveryAfterAFaultBeforePublicationYieldsExactlyOneHistoryRecord() {
    UUID eventId = auditedCreate(TENANT_A, "faulted", "corr-8", AuditedMode.SUCCEED).eventId();
    db.installAuditEventFault();

    processor.runOnce().block();
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

  // --- helpers -----------------------------------------------------------------------------

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

  private long historyRows(UUID eventId) {
    return db.count("select count(*) from audit.event where event_id = '" + eventId + "'");
  }
}
