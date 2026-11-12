package com.aisquad.owlmast.jobs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

import com.aisquad.owlmast.fixtures.jobs.DelegatingWorkRepository;
import com.aisquad.owlmast.fixtures.jobs.HeldWorkRepository;
import com.aisquad.owlmast.fixtures.jobs.HeldWorkRepository.Call;
import com.aisquad.owlmast.fixtures.notes.DbProbe;
import com.aisquad.owlmast.fixtures.notes.DbProbe.WorkRow;
import com.aisquad.owlmast.fixtures.notes.EffectStore;
import com.aisquad.owlmast.fixtures.notes.ExternalHandler;
import com.aisquad.owlmast.fixtures.notes.FollowUpHandler;
import com.aisquad.owlmast.fixtures.notes.NotesFixture;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.Failure;
import com.aisquad.owlmast.fixtures.notes.NotesFixtureConfiguration;
import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.FailedWorkItem;
import com.aisquad.owlmast.jobs.api.FailedWorkQuery;
import com.aisquad.owlmast.jobs.api.NonRetryableWorkException;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.api.WorkStatus;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.application.HandlerRegistry;
import com.aisquad.owlmast.jobs.application.TenantInternalOnlyDispatchAuthorization;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.Claim;
import com.aisquad.owlmast.jobs.port.ClaimedWork;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.platform.scope.ServiceIdentity;
import com.aisquad.owlmast.platform.scope.TenantId;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.lang.reflect.RecordComponent;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

/**
 * AC1, AC2, AC5, AC7 and AC8 against the pinned VectorChord PostgreSQL: atomic enqueue, concurrent
 * and stale claims, duplicate effect recovery, persisted retries with terminal failure, fail-closed
 * dispatch authorization and two-tenant isolation. Scheduling is off; tests drive the processor.
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
class DurableWorkIT {

  private static final ScopeContext TENANT_A = ScopeContext.of("tenant-a", "person-a");
  private static final ScopeContext TENANT_B = ScopeContext.of("tenant-b", "person-b");
  private static final ScopeContext TENANT_B_BACKEND =
      ServiceIdentity.backendScope(TENANT_B.tenant());
  private static final String SECRET = "s3cr3t-PLANTED-9f8e2c";

  @Autowired private NotesFixture notes;
  @Autowired private FollowUpHandler followUp;
  @Autowired private ExternalHandler external;
  @Autowired private EffectStore effects;
  @Autowired private DbProbe db;
  @Autowired private WorkProcessor processor;
  @Autowired private WorkEnqueue enqueue;
  @Autowired private FailedWorkQuery failedWork;
  @Autowired private ScopedTransactions transactions;
  @Autowired private WorkRepository repository;
  @Autowired private HandlerRegistry registry;
  @Autowired private RetryPolicy policy;
  @Autowired private DatabaseClient databaseClient;
  @Autowired private TransactionalOperator transactionalOperator;

  @BeforeEach
  void reset() {
    notes.ensureTable().block();
    db.clearAll();
    followUp.reset();
    effects.reset();
  }

  // --- AC1 ---------------------------------------------------------------------------------

  @Test
  void commitsTheBusinessRowAndTheWorkRecordTogether() {
    UUID noteId = createNote(TENANT_A, Failure.NONE);

    assertThat(notes.noteIds().block()).containsExactly(noteId);
    List<WorkRow> rows = db.workItems();
    assertThat(rows).hasSize(1);
    WorkRow row = rows.get(0);
    assertThat(row.status()).isEqualTo("PENDING");
    assertThat(row.tenant()).isEqualTo("tenant-a");
    assertThat(row.type()).isEqualTo(FollowUpHandler.TYPE.value());
    assertThat(row.payload()).contains(noteId.toString());
    assertThat(row.attempts()).isZero();
    assertThat(row.maxAttempts()).isEqualTo(3);
    assertThat(row.enqueuedBy()).isEqualTo("person-a");
    assertThat(row.correlationId()).isEqualTo("note:" + noteId);
  }

  @Test
  void rollbackBeforeTheEnqueueCallLeavesNeitherRowNorWorkRecord() {
    StepVerifier.create(
            notes
                .createWithFollowUp("doomed", Failure.BEFORE_ENQUEUE)
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(IllegalStateException.class)
        .verify();

    assertThat(notes.noteIds().block()).isEmpty();
    assertThat(db.workItems()).isEmpty();
  }

  @Test
  void rollbackAfterTheEnqueueCallLeavesNeitherRowNorWorkRecord() {
    StepVerifier.create(
            notes
                .createWithFollowUp("doomed", Failure.AFTER_ENQUEUE)
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectError(IllegalStateException.class)
        .verify();

    assertThat(notes.noteIds().block()).isEmpty();
    assertThat(db.workItems()).isEmpty();
  }

  @Test
  void enqueueWithoutAScopeFailsClosedBeforeAnyWrite() {
    StepVerifier.create(enqueue.enqueue(EnqueueRequest.of(FollowUpHandler.TYPE, Map.of())))
        .expectError(MissingScopeException.class)
        .verify();

    assertThat(db.workItems()).isEmpty();
  }

  // --- AC2 ---------------------------------------------------------------------------------

  @Test
  void concurrentProcessorsClaimEachItemOnceWithOneLeaseHolder() {
    for (int i = 0; i < 20; i++) {
      createNote(TENANT_A, Failure.NONE);
    }
    WorkProcessor second = independentProcessor("second-processor");
    TenantId tenant = TENANT_A.tenant();

    Mono.zip(
            processor.processTenant(tenant),
            second.processTenant(tenant),
            processor.processTenant(tenant),
            second.processTenant(tenant))
        .block();
    drain();

    List<WorkRow> rows = db.workItems();
    assertThat(rows)
        .hasSize(20)
        .allSatisfy(row -> {
          assertThat(row.status()).isEqualTo("SUCCEEDED");
          assertThat(row.attempts()).isEqualTo(1);
          assertThat(row.leaseOwner()).isIn(processor.leaseOwner(), "second-processor");
          assertThat(row.effectOutcome()).isEqualTo("APPLIED");
        });
    assertThat(followUp.invocations()).hasSize(20);
    assertThat(followUp.invocations().stream().map(FollowUpHandler.Invocation::itemId).distinct())
        .hasSize(20);
    assertThat(effects.distinctKeys()).isEqualTo(20);
    assertThat(effects.totalReceived()).as("no item ran twice").isEqualTo(20);
  }

  @Test
  void completionFromAnExpiredLeaseIsRejectedAndTheEffectIsAppliedOnceAfterReclaim() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    String key = "owlmast-work:" + itemId;
    followUp.behaveOnce(item ->
        followUp
            .applyEffect(item)
            .flatMap(outcome -> db.expireLeaseAsync(item.id()).thenReturn(outcome)));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();
    WorkRow stale = db.work(itemId);
    assertThat(stale.status()).as("rejected write changed nothing").isEqualTo("RUNNING");
    assertThat(stale.attempts()).isEqualTo(1);
    assertThat(stale.effectOutcome()).isNull();
    assertThat(stale.finishedAt()).isNull();

    processor.runOnce().block();
    WorkRow done = db.work(itemId);
    assertThat(done.status()).isEqualTo("SUCCEEDED");
    assertThat(done.attempts()).isEqualTo(2);
    assertThat(done.effectOutcome()).isEqualTo("APPLIED");
    assertThat(done.effectReference()).isEqualTo(key);
    assertThat(effects.received(key)).as("the external system saw the duplicate").isEqualTo(2);
    assertThat(effects.applied(key)).as("but applied it once").isEqualTo(1);
  }

  @Test
  void anotherProcessorReclaimsAnExpiredLeaseAndTheFirstHoldersWriteChangesNothing() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    String key = "owlmast-work:" + itemId;
    WorkProcessor second = independentProcessor("second-processor");
    followUp.behaveOnce(item ->
        db.expireLeaseAsync(item.id())
            .then(second.processTenant(item.tenant()).contextWrite(ctx -> Context.empty()))
            .then(followUp.applyEffect(item)));

    processor.runOnce().block();

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("SUCCEEDED");
    assertThat(row.leaseOwner()).isEqualTo("second-processor");
    assertThat(row.attempts()).isEqualTo(2);
    assertThat(followUp.invocations())
        .extracting(FollowUpHandler.Invocation::attempt)
        .containsExactly(1, 2);
    assertThat(effects.received(key)).isEqualTo(2);
    assertThat(effects.applied(key)).isEqualTo(1);
  }

  @Test
  void failureWriteFromAnExpiredLeaseIsRejected() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behaveOnce(item ->
        db.expireLeaseAsync(item.id()).then(Mono.error(new IllegalStateException("late failure"))));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();
    WorkRow stale = db.work(itemId);
    assertThat(stale.status()).isEqualTo("RUNNING");
    assertThat(stale.attempts()).isEqualTo(1);
    assertThat(stale.reason()).isNull();

    processor.runOnce().block();
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
  }

  @Test
  void uncertainEffectParksTheItemForReconciliationInsteadOfClaimingSuccess() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behave(item -> Mono.just(EffectOutcome.uncertain(item.idempotencyKey())));

    processor.runOnce().block();
    processor.runOnce().block();

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("OUTCOME_UNCERTAIN");
    assertThat(row.effectOutcome()).isEqualTo("UNCERTAIN");
    assertThat(row.attempts()).as("terminal: not reclaimed").isEqualTo(1);
    assertThat(terminalFailures(TENANT_A))
        .singleElement()
        .satisfies(item -> assertThat(item.status()).isEqualTo(WorkStatus.OUTCOME_UNCERTAIN));
  }

  @Test
  void theDatabaseRefusesSuccessWithoutARecordedEffectOutcome() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();

    assertThatThrownBy(() ->
            db.runSql(
                "update jobs.work_item set status = 'SUCCEEDED', finished_at = now() where id = '"
                    + itemId
                    + "'"))
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  @Test
  void aLeaseThatExpiresNaturallyWhileTheHandlerRunsCannotCommit() throws Exception {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    String key = "owlmast-work:" + itemId;
    CompletableFuture<Void> release = new CompletableFuture<>();
    // The handler applies its effect at once; its completion write, in the same transaction,
    // waits until the lease has run out on the wall clock. The handler deadline bounds only the
    // handler, so the fence alone must reject this write.
    WorkProcessor shortLease =
        new WorkProcessor(
            transactions,
            new CompletionHeldUntil(repository, release),
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofMillis(400), Duration.ofSeconds(1), 1),
            "short-lease-processor");

    CompletableFuture<Long> run = shortLease.processTenant(TENANT_A.tenant()).toFuture();
    await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() ->
            assertThat(
                    db.count(
                        "select count(*) from jobs.work_item where id = '"
                            + itemId
                            + "' and status = 'RUNNING' and lease_expires_at <= clock_timestamp()"))
                .as("the lease ran out on the wall clock before the completion write")
                .isEqualTo(1));
    release.complete(null);
    assertThat(run.get(10, TimeUnit.SECONDS)).isEqualTo(1);

    WorkRow stale = db.work(itemId);
    assertThat(stale.status())
        .as("completion after natural expiry changes nothing")
        .isEqualTo("RUNNING");
    assertThat(stale.attempts()).isEqualTo(1);
    assertThat(stale.effectOutcome()).isNull();
    assertThat(effects.received(key)).as("the handler did run to its effect").isEqualTo(1);

    processor.runOnce().block();

    WorkRow done = db.work(itemId);
    assertThat(done.status()).isEqualTo("SUCCEEDED");
    assertThat(done.attempts()).isEqualTo(2);
    assertThat(done.leaseOwner()).isEqualTo(processor.leaseOwner());
    assertThat(effects.received(key)).isEqualTo(2);
    assertThat(effects.applied(key)).isEqualTo(1);
  }

  @Test
  void itemsWaitingInABatchStayUnclaimedUntilTheirOwnDispatch() throws Exception {
    for (int i = 0; i < 5; i++) {
      createNote(TENANT_A, Failure.NONE);
    }
    List<UUID> started = new CopyOnWriteArrayList<>();
    ConcurrentMap<UUID, CompletableFuture<Void>> gates = new ConcurrentHashMap<>();
    followUp.behave(item -> {
      started.add(item.id());
      return Mono.fromFuture(gates.computeIfAbsent(item.id(), id -> new CompletableFuture<>()))
          .then(followUp.applyEffect(item));
    });

    CompletableFuture<Long> run = processor.processTenant(TENANT_A.tenant()).toFuture();
    List<WorkRow> finished = new ArrayList<>();
    for (int position = 0; position < 5; position++) {
      int expectedStarts = position + 1;
      await()
          .atMost(Duration.ofSeconds(10))
          .pollInterval(Duration.ofMillis(50))
          .until(() -> started.size() == expectedStarts);
      UUID current = started.get(position);
      WorkRow running = db.work(current);
      assertThat(running.status()).isEqualTo("RUNNING");
      assertThat(running.attempts()).isEqualTo(1);
      assertThat(db.workItems())
          .filteredOn(row -> !row.id().equals(current) && !started.contains(row.id()))
          .as("items behind the running one hold no lease yet")
          .hasSize(4 - position)
          .allSatisfy(row -> {
            assertThat(row.status()).isEqualTo("PENDING");
            assertThat(row.leaseToken()).isNull();
            assertThat(row.leaseOwner()).isNull();
            assertThat(row.attempts()).isZero();
          });
      gates.computeIfAbsent(current, id -> new CompletableFuture<>()).complete(null);
      await()
          .atMost(Duration.ofSeconds(10))
          .pollInterval(Duration.ofMillis(50))
          .until(() -> db.work(current).status().equals("SUCCEEDED"));
      finished.add(db.work(current));
    }
    assertThat(run.get(10, TimeUnit.SECONDS)).isEqualTo(5);

    assertThat(finished).hasSize(5).allSatisfy(row -> assertThat(row.attempts()).isEqualTo(1));
    for (int position = 1; position < finished.size(); position++) {
      WorkRow previous = finished.get(position - 1);
      WorkRow next = finished.get(position);
      assertThat(next.leaseExpiresAt().minus(policy.leaseDuration()))
          .as("each lease was taken after the previous item finished")
          .isAfterOrEqualTo(previous.finishedAt());
    }
    assertThat(effects.totalReceived()).isEqualTo(5);
  }

  // --- AC5 ---------------------------------------------------------------------------------

  @Test
  void retriesPersistAttemptsCappedBackoffAndSafeReasonThenFailTerminally(CapturedOutput output) {
    createNote(TENANT_A, Failure.NONE, SECRET);
    UUID itemId = db.workItems().get(0).id();
    followUp.behave(item -> Mono.error(new IllegalStateException("handler saw " + SECRET)));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();
    WorkRow first = db.work(itemId);
    assertThat(first.status()).isEqualTo("PENDING");
    assertThat(first.attempts()).isEqualTo(1);
    assertThat(first.reason()).isEqualTo("IllegalStateException");
    assertThat(backoffOf(first)).isBetween(Duration.ofMillis(80), Duration.ofMillis(300));

    awaitAttempt(itemId, 2);
    WorkRow second = db.work(itemId);
    assertThat(second.status()).isEqualTo("PENDING");
    assertThat(backoffOf(second)).isBetween(Duration.ofMillis(180), Duration.ofMillis(500));

    awaitAttempt(itemId, 3);
    WorkRow terminal = db.work(itemId);
    assertThat(terminal.status()).isEqualTo("FAILED");
    assertThat(terminal.finishedAt()).isNotNull();
    assertThat(terminal.reason()).isEqualTo("IllegalStateException");

    processor.runOnce().block();
    assertThat(db.work(itemId).attempts()).as("terminal items are not reclaimed").isEqualTo(3);

    List<FailedWorkItem> listed = terminalFailures(TENANT_A);
    assertThat(listed)
        .singleElement()
        .satisfies(item -> {
          assertThat(item.id()).isEqualTo(itemId);
          assertThat(item.tenant()).isEqualTo(TENANT_A.tenant());
          assertThat(item.type()).isEqualTo(FollowUpHandler.TYPE);
          assertThat(item.status()).isEqualTo(WorkStatus.FAILED);
          assertThat(item.attemptCount()).isEqualTo(3);
          assertThat(item.safeReason()).contains("IllegalStateException");
        });
    assertThat(
            Arrays.stream(FailedWorkItem.class.getRecordComponents()).map(RecordComponent::getName))
        .noneMatch(name -> name.toLowerCase(java.util.Locale.ROOT).contains("payload"));
    assertThat(db.rowsAsText("jobs.work_item")).noneMatch(row -> row.contains(SECRET));
    assertThat(output.getAll()).doesNotContain(SECRET);
  }

  @Test
  void aLeaseExpiringAfterTheLastPermittedAttemptMakesTheItemTerminal() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    db.runSql("update jobs.work_item set attempt_count = 2 where id = '" + itemId + "'");
    followUp.behaveOnce(item ->
        db.expireLeaseAsync(item.id()).then(Mono.error(new IllegalStateException("holder died"))));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();
    assertThat(db.work(itemId).status()).isEqualTo("RUNNING");
    assertThat(db.work(itemId).attempts()).isEqualTo(3);

    processor.runOnce().block();
    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("FAILED");
    assertThat(row.reason()).isEqualTo("lease-expired-attempts-exhausted");
    assertThat(followUp.invocations()).hasSize(1);
  }

  @Test
  void aHandlerStillRunningAtItsDeadlineIsCancelledAndTheRestOfTheBatchRuns() {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_A, Failure.NONE);
    followUp.behaveOnce(item -> Mono.never());

    assertThat(
            shortDeadlineProcessor().processTenant(TENANT_A.tenant()).block(Duration.ofSeconds(10)))
        .as("the hung handler did not stall the batch")
        .isEqualTo(2L);

    assertThat(db.workItems())
        .extracting(WorkRow::status)
        .containsExactlyInAnyOrder("PENDING", "SUCCEEDED");
    WorkRow overrun =
        db.workItems().stream()
            .filter(row -> row.status().equals("PENDING"))
            .findFirst()
            .orElseThrow();
    assertThat(overrun.attempts()).isEqualTo(1);
    assertThat(overrun.reason()).isEqualTo("handler-deadline-exceeded");
    assertThat(overrun.nextAttemptAt()).isAfter(overrun.updatedAt());
  }

  @Test
  void aHandlerBlockedInsideTheDatabaseIsCancelledByTheServerBeforeItsLeaseRunsOut() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behaveOnce(item ->
        databaseClient
            .sql("select pg_sleep(60)")
            .fetch()
            .rowsUpdated()
            .then(Mono.<EffectOutcome>never()));

    assertThat(
            shortDeadlineProcessor().processTenant(TENANT_A.tenant()).block(Duration.ofSeconds(10)))
        .as("the rollback did not wait behind the sleeping statement")
        .isEqualTo(1L);

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("PENDING");
    assertThat(row.attempts()).isEqualTo(1);
    assertThat(row.reason()).isEqualTo("handler-deadline-exceeded");
  }

  @Test
  void aHandlerThatCompletesWithoutAnEffectOutcomeIsRetriedWithASafeReason() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behave(item -> Mono.empty());

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("PENDING");
    assertThat(row.attempts()).isEqualTo(1);
    assertThat(row.reason()).isEqualTo("handler-returned-no-effect-outcome");
    assertThat(row.effectOutcome()).isNull();
  }

  @Test
  void aPerItemAttemptLimitOverridesTheConfiguredMaximum() {
    UUID itemId =
        transactions
            .inTransaction(scope ->
                enqueue.enqueue(
                    EnqueueRequest.of(FollowUpHandler.TYPE, Map.of()).withMaxAttempts(1)))
            .contextWrite(Scopes.bind(TENANT_A))
            .block();
    followUp.behave(item -> Mono.error(new IllegalStateException("always fails")));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();

    WorkRow row = db.work(itemId);
    assertThat(row.maxAttempts()).isEqualTo(1);
    assertThat(row.status()).isEqualTo("FAILED");
    assertThat(row.attempts()).isEqualTo(1);
  }

  @Test
  void aCompletionRecordsTheWallClockTimeTheHandlerFinished() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behaveOnce(
        item -> Mono.delay(Duration.ofMillis(400)).then(followUp.applyEffect(item)));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("SUCCEEDED");
    OffsetDateTime claimedAt = row.leaseExpiresAt().minus(policy.leaseDuration());
    assertThat(Duration.between(claimedAt, row.finishedAt()))
        .as("finished_at is taken when the completion is written, not when its transaction began")
        .isGreaterThanOrEqualTo(Duration.ofMillis(350));
  }

  // --- AC7 ---------------------------------------------------------------------------------

  @Test
  void theDefaultRecheckDeniesHandlersThatAreNotTenantInternalWithoutInvokingThem() {
    UUID itemId = enqueueOnly(TENANT_A, ExternalHandler.TYPE);

    processor.runOnce().block();

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("DENIED");
    assertThat(row.reason()).isEqualTo("authorization-denied");
    assertThat(row.finishedAt()).isNotNull();
    assertThat(external.invocations()).isZero();
    assertThat(terminalFailures(TENANT_A))
        .singleElement()
        .satisfies(item -> assertThat(item.status()).isEqualTo(WorkStatus.DENIED));
  }

  @Test
  void anUndecidedRecheckBlocksTheAttemptWithoutInvokingTheHandler(CapturedOutput output) {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor undecided =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) ->
                Mono.error(new IllegalStateException("authorization unavailable")),
            singleItemPolicy(),
            "undecided-processor");
    WorkProcessor silent =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) -> Mono.just(DispatchDecision.UNDECIDED),
            singleItemPolicy(),
            "silent-processor");

    assertThat(undecided.processTenant(TENANT_A.tenant()).block()).isEqualTo(1L);
    WorkRow blocked = db.work(itemId);
    assertThat(blocked.status()).isEqualTo("PENDING");
    assertThat(blocked.attempts()).as("a blocked attempt is given back uncounted").isZero();
    assertThat(blocked.reason()).isEqualTo("authorization-undecided");
    assertThat(blocked.leaseToken()).isNull();
    assertThat(backoffOf(blocked)).isBetween(Duration.ofMillis(80), Duration.ofMillis(150));
    assertThat(releaseCount(itemId)).isEqualTo(1);
    assertThat(followUp.invocations()).isEmpty();

    // More blocked rounds than the attempt budget: an outage of the deciding component never
    // makes the item terminal.
    for (int round = 0; round < policy.maxAttempts() + 1; round++) {
      await()
          .atMost(Duration.ofSeconds(5))
          .pollInterval(Duration.ofMillis(50))
          .untilAsserted(
              () -> assertThat(silent.processTenant(TENANT_A.tenant()).block()).isEqualTo(1L));
      assertThat(db.work(itemId).attempts()).isZero();
      assertThat(db.work(itemId).status()).isEqualTo("PENDING");
      assertThat(releaseCount(itemId)).as("consecutive releases are counted").isEqualTo(round + 2);
    }
    assertThat(followUp.invocations()).isEmpty();
    assertThat(backoffOf(db.work(itemId)))
        .as("releases back off exponentially (0.1 s, 0.2 s, 0.4 s) up to the 0.4 s cap")
        .isBetween(Duration.ofMillis(380), Duration.ofMillis(450));
    assertThat(output.getAll())
        .as("a blocked item never becomes terminal, so it is reported once past the limit")
        .contains("has been released " + policy.maxAttempts() + " times in a row")
        .contains("has been released " + (policy.maxAttempts() + 2) + " times in a row")
        .as("releases below the attempt limit are not reported at WARN")
        .doesNotContain("has been released 1 times in a row")
        .doesNotContain("has been released " + (policy.maxAttempts() - 1) + " times in a row");

    awaitAttempt(itemId, 1);
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
    assertThat(db.work(itemId).reason()).isNull();
    assertThat(releaseCount(itemId)).as("a dispatch that ran ends the blocked streak").isZero();
  }

  @Test
  void aReleaseFromAnExpiredLeaseIsRejected() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor lateUndecided =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) ->
                db.expireLeaseAsync(item.id()).thenReturn(DispatchDecision.UNDECIDED),
            singleItemPolicy(),
            "late-undecided-processor");

    lateUndecided.processTenant(TENANT_A.tenant()).block();

    WorkRow stale = db.work(itemId);
    assertThat(stale.status()).as("the fenced release changed nothing").isEqualTo("RUNNING");
    assertThat(stale.attempts()).as("the attempt count was not restored").isEqualTo(1);
    assertThat(stale.reason()).isNull();
    assertThat(stale.leaseToken()).as("the fencing token was not cleared").isNotNull();
    assertThat(releaseCount(itemId)).isZero();
    assertThat(followUp.invocations()).isEmpty();

    processor.runOnce().block();
    WorkRow done = db.work(itemId);
    assertThat(done.status()).isEqualTo("SUCCEEDED");
    assertThat(done.attempts()).isEqualTo(2);
  }

  @Test
  void anAnswerPastTheRechecksShareReleasesTheItemInsteadOfChargingTheHandler() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    RetryPolicy halfSecondDeadline =
        new RetryPolicy(
            policy.maxAttempts(),
            policy.backoffBase(),
            policy.backoffCap(),
            Duration.ofSeconds(5),
            1,
            Duration.ofMillis(500));
    WorkProcessor lateAllow =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) ->
                Mono.delay(Duration.ofMillis(450)).thenReturn(DispatchDecision.ALLOW),
            halfSecondDeadline,
            "late-allow-processor");

    lateAllow.processTenant(TENANT_A.tenant()).block(Duration.ofSeconds(10));

    WorkRow released = db.work(itemId);
    assertThat(released.status()).isEqualTo("PENDING");
    assertThat(released.attempts())
        .as("an ALLOW that left the handler 50 ms of a 500 ms deadline is not a failed attempt")
        .isZero();
    assertThat(released.reason()).isEqualTo("authorization-undecided");
    assertThat(followUp.invocations()).as("the handler was never started").isEmpty();

    awaitAttempt(itemId, 1);
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
  }

  @Test
  void aCancelledDispatchGivesItsItemBackAtOnceAndUncounted() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    CompletableFuture<Void> started = new CompletableFuture<>();
    followUp.behaveOnce(item -> {
      started.complete(null);
      return Mono.never();
    });
    WorkProcessor single = singleItemProcessor();

    Disposable wakeUp = single.processTenant(TENANT_A.tenant()).subscribe();
    started.orTimeout(10, TimeUnit.SECONDS).join();
    assertThat(db.work(itemId).status()).isEqualTo("RUNNING");
    wakeUp.dispose();
    single.quiesce().block(Duration.ofSeconds(10));

    WorkRow givenBack = db.work(itemId);
    assertThat(givenBack.status())
        .as("a shutdown does not leave the item RUNNING until its lease expires")
        .isEqualTo("PENDING");
    assertThat(givenBack.attempts()).as("the cancelled attempt is not counted").isZero();
    assertThat(givenBack.reason()).isEqualTo("dispatch-cancelled");
    assertThat(givenBack.leaseToken()).isNull();
    assertThat(backoffOf(givenBack)).as("due at once").isLessThan(Duration.ofMillis(50));
    assertThat(releaseCount(itemId)).as("not a blocked release").isZero();

    assertThat(processor.runOnce().block()).isEqualTo(1L);
    WorkRow done = db.work(itemId);
    assertThat(done.status()).isEqualTo("SUCCEEDED");
    assertThat(done.attempts()).isEqualTo(1);
  }

  @Test
  void aGiveBackFromAnExpiredOrReplacedLeaseIsRejected() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    ScopeContext backend = ServiceIdentity.backendScope(TENANT_A.tenant());
    ClaimedWork claimed = claimOne("cancelled-holder");

    assertThat(giveBack(backend, UUID.randomUUID()))
        .as("another lease's token gives nothing back")
        .isZero();
    assertThat(giveBack(TENANT_B_BACKEND, claimed.leaseToken()))
        .as("a token gives nothing back under another tenant's scope")
        .isZero();
    db.expireLeaseAsync(itemId).block();
    assertThat(giveBack(backend, claimed.leaseToken()))
        .as("a cancellation that arrives after the lease ran out gives nothing back")
        .isZero();

    WorkRow untouched = db.work(itemId);
    assertThat(untouched.status()).isEqualTo("RUNNING");
    assertThat(untouched.attempts()).isEqualTo(1);
    assertThat(untouched.reason()).isNull();
    assertThat(untouched.leaseToken()).isEqualTo(claimed.leaseToken());
  }

  @Test
  void aStalledStepFailsTheTenantInsteadOfStoppingTheWakeUp(CapturedOutput output) {
    RetryPolicy oneSecondSteps =
        new RetryPolicy(
            policy.maxAttempts(),
            policy.backoffBase(),
            policy.backoffCap(),
            Duration.ofSeconds(1),
            1);
    for (Call stalled : List.of(Call.SWEEP, Call.CLAIM, Call.RELEASE, Call.DENY, Call.FAIL)) {
      db.clearAll();
      followUp.reset();
      createNote(TENANT_A, Failure.NONE);
      createNote(TENANT_B, Failure.NONE);
      // Whichever tenant is served first meets the stalled step; the other one is unaffected.
      AtomicBoolean first = new AtomicBoolean(true);
      DispatchDecision firstDecision =
          switch (stalled) {
            case RELEASE -> DispatchDecision.UNDECIDED;
            case DENY -> DispatchDecision.DENY;
            default -> DispatchDecision.ALLOW;
          };
      if (stalled == Call.FAIL) {
        followUp.behaveOnce(item -> Mono.error(new IllegalStateException("fixture failure")));
      }
      WorkProcessor overStalledStep =
          new WorkProcessor(
              transactions,
              new HeldWorkRepository(repository, stalled),
              registry,
              (item, registration) ->
                  Mono.just(
                      first.compareAndSet(true, false) ? firstDecision : DispatchDecision.ALLOW),
              oneSecondSteps,
              "stalled-" + stalled + "-processor");

      assertThat(overStalledStep.runOnce().block(Duration.ofSeconds(10)))
          .as("one tenant's %s never answers; the wake-up still ends and serves the other", stalled)
          .isEqualTo(1L);
      assertThat(db.workItems())
          .as("after a stalled %s", stalled)
          .extracting(WorkRow::status)
          .containsExactlyInAnyOrder(
              // A stalled write leaves the item under its lease; before the claim it is untouched.
              stalled == Call.SWEEP || stalled == Call.CLAIM ? "PENDING" : "RUNNING", "SUCCEEDED");
    }
    assertThat(output.getAll()).contains("failed: TimeoutException");

    WorkProcessor overStalledDiscovery =
        new WorkProcessor(
            transactions,
            new HeldWorkRepository(repository, Call.DISCOVERY),
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            oneSecondSteps,
            "stalled-discovery-processor");
    StepVerifier.create(overStalledDiscovery.runOnce())
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(10));
  }

  @Test
  void aStatementTheProcessorGaveUpOnIsCancelledByTheServerToo() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor oneSecondSteps =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            new RetryPolicy(
                policy.maxAttempts(),
                policy.backoffBase(),
                policy.backoffCap(),
                Duration.ofSeconds(1),
                1),
            "locked-out-processor");
    CompletableFuture<Void> locked = new CompletableFuture<>();
    CompletableFuture<Void> unlock = new CompletableFuture<>();
    Mono<Void> tableLock =
        transactionalOperator
            .execute(transaction ->
                databaseClient
                    .sql("lock table jobs.work_item in access exclusive mode")
                    .then()
                    .doOnSuccess(done -> locked.complete(null))
                    .then(Mono.fromCompletionStage(unlock)))
            .then()
            .cache();
    tableLock.subscribe();
    try {
      locked.orTimeout(10, TimeUnit.SECONDS).join();

      // Tenant discovery (its own transaction) and a scoped step (the sweep) both wait for the
      // lock. The client gives up after one second; the server must end the statement as well.
      for (Mono<Long> blocked :
          List.of(oneSecondSteps.runOnce(), oneSecondSteps.processTenant(TENANT_A.tenant()))) {
        CompletableFuture<Long> outcome = blocked.toFuture();
        await()
            .atMost(Duration.ofSeconds(5))
            .pollInterval(Duration.ofMillis(25))
            .untilAsserted(() -> assertThat(statementsWaitingForTheWorkTable()).isEqualTo(1));
        assertThatThrownBy(() -> outcome.get(10, TimeUnit.SECONDS))
            .as("the step fails; it does not wait for the lock")
            .isInstanceOf(ExecutionException.class);
        await()
            .atMost(Duration.ofSeconds(5))
            .pollInterval(Duration.ofMillis(25))
            .untilAsserted(() ->
                assertThat(statementsWaitingForTheWorkTable())
                    .as("statement_timeout ended the statement although the lock is still held")
                    .isZero());
      }
    } finally {
      unlock.complete(null);
      tableLock.block(Duration.ofSeconds(10));
    }

    assertThat(processor.runOnce().block()).isEqualTo(1L);
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
  }

  @Test
  void aShutdownDuringTheFailureWriteRecordsTheFailureInsteadOfGivingTheItemBack() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behave(item -> Mono.error(new NonRetryableWorkException("the note is gone")));
    HeldWorkRepository heldFailure = new HeldWorkRepository(repository, Call.FAIL);
    WorkProcessor single =
        new WorkProcessor(
            transactions,
            heldFailure,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            singleItemPolicy(),
            "held-failure-processor");

    Disposable wakeUp = single.processTenant(TENANT_A.tenant()).subscribe();
    heldFailure.entered().orTimeout(10, TimeUnit.SECONDS).join();
    assertThat(db.work(itemId).status()).isEqualTo("RUNNING");
    wakeUp.dispose();
    single.quiesce().block(Duration.ofSeconds(10));

    WorkRow failed = db.work(itemId);
    assertThat(failed.status())
        .as("the handler had already failed for good; the shutdown does not erase that")
        .isEqualTo("FAILED");
    assertThat(failed.attempts()).as("the failed attempt counts").isEqualTo(1);
    assertThat(failed.reason()).isEqualTo("NonRetryableWorkException");
    assertThat(failed.finishedAt()).isNotNull();
    assertThat(failed.leaseToken()).isNull();

    processor.runOnce().block();
    assertThat(followUp.invocations()).as("the item is not run again").hasSize(1);
  }

  @Test
  void aShutdownDuringTheDenialWriteStillDeniesTheItem() {
    UUID itemId = enqueueOnly(TENANT_A, ExternalHandler.TYPE);
    HeldWorkRepository heldDenial = new HeldWorkRepository(repository, Call.DENY);
    WorkProcessor single =
        new WorkProcessor(
            transactions,
            heldDenial,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            singleItemPolicy(),
            "held-denial-processor");

    Disposable wakeUp = single.processTenant(TENANT_A.tenant()).subscribe();
    heldDenial.entered().orTimeout(10, TimeUnit.SECONDS).join();
    wakeUp.dispose();
    single.quiesce().block(Duration.ofSeconds(10));

    WorkRow denied = db.work(itemId);
    assertThat(denied.status()).isEqualTo("DENIED");
    assertThat(denied.attempts()).isEqualTo(1);
    assertThat(denied.reason()).isEqualTo("authorization-denied");
    assertThat(external.invocations()).isZero();
  }

  @Test
  void aClaimWhoseAnswerNeverArrivedIsGivenBackWhenItsDispatchIsCancelled() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    ClaimAnswerLost lostAnswer = new ClaimAnswerLost(repository);
    WorkProcessor single =
        new WorkProcessor(
            transactions,
            lostAnswer,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            singleItemPolicy(),
            "lost-answer-processor");

    Disposable wakeUp = single.processTenant(TENANT_A.tenant()).subscribe();
    lostAnswer.committed().orTimeout(10, TimeUnit.SECONDS).join();
    WorkRow claimed = db.work(itemId);
    assertThat(claimed.status()).as("the claim committed").isEqualTo("RUNNING");
    assertThat(claimed.attempts()).isEqualTo(1);
    wakeUp.dispose();
    single.quiesce().block(Duration.ofSeconds(10));

    WorkRow givenBack = db.work(itemId);
    assertThat(givenBack.status())
        .as("the processor never saw the row, but it knows the lease token it claimed with")
        .isEqualTo("PENDING");
    assertThat(givenBack.attempts()).as("the handler never ran; no attempt is used").isZero();
    assertThat(givenBack.reason()).isEqualTo("dispatch-cancelled");
    assertThat(givenBack.leaseToken()).isNull();
    assertThat(followUp.invocations()).isEmpty();

    assertThat(processor.runOnce().block()).isEqualTo(1L);
    assertThat(db.work(itemId).attempts()).isEqualTo(1);
  }

  @Test
  void aClaimStillCommittingWhenItsDispatchIsCancelledIsGivenBackOnceTheCommitLands() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor single = singleItemProcessor();
    db.installSlowClaimCommit(Duration.ofSeconds(2));
    try {
      Disposable wakeUp = single.processTenant(TENANT_A.tenant()).subscribe();
      await()
          .atMost(Duration.ofSeconds(10))
          .pollInterval(Duration.ofMillis(25))
          .untilAsserted(() ->
              assertThat(db.commitsInFlight()).as("the claim is inside its COMMIT").isEqualTo(1));
      assertThat(db.work(itemId).status())
          .as("no other session sees the claim yet")
          .isEqualTo("PENDING");
      wakeUp.dispose();
      single.quiesce().block(Duration.ofSeconds(10));
      await()
          .atMost(Duration.ofSeconds(10))
          .pollInterval(Duration.ofMillis(25))
          .untilAsserted(() -> assertThat(db.commitsInFlight()).isZero());
    } finally {
      db.removeSlowClaimCommit();
    }

    WorkRow givenBack = db.work(itemId);
    assertThat(givenBack.status())
        .as("the give-back waited for the claim's commit instead of finding nothing to give back")
        .isEqualTo("PENDING");
    assertThat(givenBack.attempts()).as("the handler never ran; no attempt is used").isZero();
    assertThat(givenBack.reason()).isEqualTo("dispatch-cancelled");
    assertThat(givenBack.leaseToken()).isNull();
    assertThat(followUp.invocations()).isEmpty();

    assertThat(processor.runOnce().block()).isEqualTo(1L);
    assertThat(db.work(itemId).attempts()).isEqualTo(1);
  }

  @Test
  void aShutdownDuringTheRollbackOfAFailedHandlerRecordsTheFailure() throws Exception {
    UUID itemId =
        transactions
            .inTransaction(scope ->
                enqueue.enqueue(
                    EnqueueRequest.of(FollowUpHandler.TYPE, Map.of()).withMaxAttempts(1)))
            .contextWrite(Scopes.bind(TENANT_A))
            .block();
    CompletableFuture<Void> deadlineFired = new CompletableFuture<>();
    // The statement outlives the handler deadline, so the rollback queues behind it on the same
    // connection until the server ends it (statement_timeout, 2.75 s into this 5 s lease).
    followUp.behaveOnce(item ->
        databaseClient
            .sql("select pg_sleep(60)")
            .fetch()
            .rowsUpdated()
            .then(Mono.<EffectOutcome>never())
            .doOnCancel(() -> deadlineFired.complete(null)));
    HeldWorkRepository watched = new HeldWorkRepository(repository, Call.FAIL);
    WorkProcessor single =
        new WorkProcessor(
            transactions,
            watched,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            new RetryPolicy(
                policy.maxAttempts(),
                policy.backoffBase(),
                policy.backoffCap(),
                Duration.ofSeconds(5),
                1,
                Duration.ofMillis(500)),
            "rollback-shutdown-processor");

    Disposable wakeUp = single.processTenant(TENANT_A.tenant()).subscribe();
    deadlineFired.orTimeout(10, TimeUnit.SECONDS).join();
    // The deadline cancels the handler and then fails the attempt on the same thread; this pause
    // only lets that thread finish, and is far inside the two seconds the rollback still waits.
    Thread.sleep(200);
    assertThat(watched.entered())
        .as("the transaction is still rolling back; the failure write has not started")
        .isNotDone();
    wakeUp.dispose();
    watched.release();
    single.quiesce().block(Duration.ofSeconds(10));

    WorkRow failed = db.work(itemId);
    assertThat(failed.status())
        .as("the last attempt had already failed; the shutdown does not hand it back uncounted")
        .isEqualTo("FAILED");
    assertThat(failed.attempts()).as("the failed attempt counts").isEqualTo(1);
    assertThat(failed.reason()).isEqualTo("handler-deadline-exceeded");
    assertThat(failed.finishedAt()).isNotNull();
    assertThat(failed.leaseToken()).isNull();
  }

  @Test
  void aShutdownDuringTheFailureWriteOfAFailedCompletionRecordsTheFailure() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    // The handler succeeds and the completion write fails, so the attempt fails outside the
    // handler: only the failure write itself marks the outcome as decided.
    HeldWorkRepository heldFailure =
        new HeldWorkRepository(new FailingCompletion(repository), Call.FAIL);
    WorkProcessor single =
        new WorkProcessor(
            transactions,
            heldFailure,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            singleItemPolicy(),
            "failed-completion-processor");

    Disposable wakeUp = single.processTenant(TENANT_A.tenant()).subscribe();
    heldFailure.entered().orTimeout(10, TimeUnit.SECONDS).join();
    wakeUp.dispose();
    single.quiesce().block(Duration.ofSeconds(10));

    WorkRow failed = db.work(itemId);
    assertThat(failed.attempts())
        .as("the attempt failed before the shutdown; it is not handed back uncounted")
        .isEqualTo(1);
    assertThat(failed.status()).isEqualTo("PENDING");
    assertThat(failed.reason()).isEqualTo("IllegalStateException");
    assertThat(failed.nextAttemptAt()).as("retried with backoff").isAfter(failed.updatedAt());
  }

  @Test
  void aBatchThatEndsNormallyGivesNothingBack() {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_A, Failure.NONE);
    HeldWorkRepository watched = new HeldWorkRepository(repository, Call.GIVE_BACK);
    WorkProcessor overWatched =
        new WorkProcessor(
            transactions,
            watched,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            policy,
            "watched-processor");

    assertThat(overWatched.runOnce().block()).isEqualTo(2L);
    overWatched.quiesce().block(Duration.ofSeconds(10));

    assertThat(watched.entered())
        .as("the batch ends by cancelling its source; that is not a cancelled dispatch")
        .isNotDone();
    assertThat(db.workItems()).allSatisfy(row -> assertThat(row.status()).isEqualTo("SUCCEEDED"));
  }

  @Test
  void theDispatchClockStartsBeforeTheClaimSoALateAnswerIsNotChargedToTheHandler() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    RetryPolicy halfSecondDeadline =
        new RetryPolicy(
            policy.maxAttempts(),
            policy.backoffBase(),
            policy.backoffCap(),
            Duration.ofSeconds(5),
            1,
            Duration.ofMillis(500));

    // The claim answers 300 ms after the lease started: past the recheck's 250 ms share. The
    // recheck then allows at once, which no timeout preempts; the item is released, not run.
    lateClaimProcessor(Duration.ofMillis(300), halfSecondDeadline)
        .processTenant(TENANT_A.tenant())
        .block(Duration.ofSeconds(10));

    WorkRow released = db.work(itemId);
    assertThat(released.status()).isEqualTo("PENDING");
    assertThat(released.attempts()).as("released uncounted").isZero();
    assertThat(released.reason()).isEqualTo("authorization-undecided");
    assertThat(followUp.invocations()).as("the handler was never started").isEmpty();

    // The claim answers 150 ms late and the handler needs 400 ms: 550 ms of the lease, which is
    // past the 500 ms deadline although the handler itself stayed under it.
    followUp.behave(item -> Mono.delay(Duration.ofMillis(400)).then(followUp.applyEffect(item)));
    db.runSql("update jobs.work_item set next_attempt_at = now() where id = '" + itemId + "'");
    lateClaimProcessor(Duration.ofMillis(150), halfSecondDeadline)
        .processTenant(TENANT_A.tenant())
        .block(Duration.ofSeconds(10));

    WorkRow overrun = db.work(itemId);
    assertThat(overrun.status()).isEqualTo("PENDING");
    assertThat(overrun.attempts()).isEqualTo(1);
    assertThat(overrun.reason()).isEqualTo("handler-deadline-exceeded");
  }

  @Test
  void aRecheckThatNeverAnswersIsReleasedAtItsShareOfTheDeadline() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor silentRecheck =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) -> Mono.never(),
            new RetryPolicy(
                policy.maxAttempts(),
                policy.backoffBase(),
                policy.backoffCap(),
                Duration.ofSeconds(10),
                1,
                Duration.ofSeconds(4)),
            "silent-recheck-processor");

    assertThat(silentRecheck.processTenant(TENANT_A.tenant()).block(Duration.ofMillis(3500)))
        .as("released after the recheck's 2 s share, not after the 4 s handler deadline")
        .isEqualTo(1L);

    WorkRow released = db.work(itemId);
    assertThat(released.status()).isEqualTo("PENDING");
    assertThat(released.attempts()).isZero();
    assertThat(released.reason()).isEqualTo("authorization-undecided");
  }

  @Test
  void aFailedAttemptEndsTheStreakOfReleases() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor silent =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) -> Mono.just(DispatchDecision.UNDECIDED),
            singleItemPolicy(),
            "silent-processor");
    for (int releases = 1; releases <= 2; releases++) {
      int expected = releases;
      await()
          .atMost(Duration.ofSeconds(5))
          .pollInterval(Duration.ofMillis(50))
          .untilAsserted(() -> {
            silent.processTenant(TENANT_A.tenant()).block();
            assertThat(releaseCount(itemId)).isEqualTo(expected);
          });
    }
    assertThat(backoffOf(db.work(itemId)))
        .isBetween(Duration.ofMillis(180), Duration.ofMillis(250));

    followUp.behaveOnce(item -> Mono.error(new IllegalStateException("fixture failure")));
    awaitAttempt(itemId, 1);

    WorkRow failed = db.work(itemId);
    assertThat(failed.status()).isEqualTo("PENDING");
    assertThat(failed.reason()).isEqualTo("IllegalStateException");
    assertThat(releaseCount(itemId)).as("a recorded failure ends the streak").isZero();

    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          silent.processTenant(TENANT_A.tenant()).block();
          assertThat(releaseCount(itemId)).isEqualTo(1);
        });
    assertThat(backoffOf(db.work(itemId)))
        .as("the next release starts again from the backoff base")
        .isBetween(Duration.ofMillis(80), Duration.ofMillis(150));
  }

  @Test
  void aReclaimOfAnExpiredLeaseEndsTheStreakOfReleases() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) -> Mono.just(DispatchDecision.UNDECIDED),
            singleItemPolicy(),
            "silent-processor")
        .processTenant(TENANT_A.tenant())
        .block();
    assertThat(releaseCount(itemId)).isEqualTo(1);
    db.runSql("update jobs.work_item set next_attempt_at = now() where id = '" + itemId + "'");

    claimOne("first-holder");
    assertThat(releaseCount(itemId))
        .as("a claim of a pending item says nothing about the handler yet")
        .isEqualTo(1);

    // The first holder got past the recheck and then lost its lease: no fenced write of its own
    // can reset the count any more.
    db.expireLeaseAsync(itemId).block();
    claimOne("reclaimer");

    assertThat(db.work(itemId).attempts()).isEqualTo(2);
    assertThat(releaseCount(itemId))
        .as("the reclaimed attempt was not a release, so the streak is over")
        .isZero();
  }

  @Test
  void aCompletionThatNeverAnswersEndsWithTheLeaseInsteadOfHoldingTheWakeUp() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor overSilentCompletion =
        new WorkProcessor(
            transactions,
            new CompletionHeldUntil(repository, new CompletableFuture<>()),
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofMillis(400), Duration.ofSeconds(1), 1),
            "silent-completion-processor");

    assertThat(overSilentCompletion.processTenant(TENANT_A.tenant()).block(Duration.ofSeconds(10)))
        .as("the dispatch ended although its completion write never answered")
        .isEqualTo(1L);

    WorkRow expired = db.work(itemId);
    assertThat(expired.status())
        .as("past the lease no write of that dispatch counts, the failure write included")
        .isEqualTo("RUNNING");
    assertThat(expired.attempts()).isEqualTo(1);
    assertThat(expired.reason()).isNull();

    processor.runOnce().block();
    WorkRow done = db.work(itemId);
    assertThat(done.status()).isEqualTo("SUCCEEDED");
    assertThat(done.attempts()).isEqualTo(2);
  }

  @Test
  void enqueueRejectsAWorkTypeNoHandlerRegistersBeforeAnyWrite() {
    StepVerifier.create(
            notes
                .enqueueOnly(WorkType.of("fixture.unknown"), Map.of())
                .contextWrite(Scopes.bind(TENANT_A)))
        .expectErrorSatisfies(error ->
            assertThat(error)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("fixture.unknown"))
        .verify();
    assertThat(db.workItems()).as("an item no instance would ever claim is never stored").isEmpty();

    assertThat(enqueueOnly(TENANT_A, FollowUpHandler.TYPE)).isNotNull();
    assertThat(db.workItems()).hasSize(1);
  }

  @Test
  void workThisInstanceCannotRunIsLeftForAnInstanceThatCan() {
    // Enqueue refuses unregistered types, so the row of a newer build is written directly.
    UUID unknownType = enqueueOnly(TENANT_A, FollowUpHandler.TYPE);
    db.runSql(
        "update jobs.work_item set work_type = 'fixture.unknown' where id = '" + unknownType + "'");
    UUID newerVersion = enqueueOnly(TENANT_A, FollowUpHandler.TYPE);
    db.runSql(
        "update jobs.work_item set contract_version = "
            + (WorkItemContract.VERSION + 1)
            + " where id = '"
            + newerVersion
            + "'");

    assertThat(
            repository
                .tenantsWithDueWork(10, registry.types(), policy.stepTimeout())
                .collectList()
                .block())
        .as("a tenant with only work this instance cannot run is not discovered")
        .isEmpty();
    assertThat(processor.runOnce().block()).isZero();
    assertThat(processor.processTenant(TENANT_A.tenant()).block()).isZero();

    for (UUID itemId : List.of(unknownType, newerVersion)) {
      WorkRow row = db.work(itemId);
      assertThat(row.status()).isEqualTo("PENDING");
      assertThat(row.attempts())
          .as("no attempt was consumed by an instance without the handler")
          .isZero();
      assertThat(row.reason()).isNull();
      assertThat(row.leaseToken()).isNull();
    }
    assertThat(followUp.invocations()).isEmpty();

    createNote(TENANT_A, Failure.NONE);
    assertThat(processor.runOnce().block())
        .as("runnable work in the same tenant still flows")
        .isEqualTo(1L);
  }

  // --- AC8 ---------------------------------------------------------------------------------

  @Test
  void claimsRunUnderEachItemsOwnTenantAndListingsStayWithinTheBoundTenant() {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_B, Failure.NONE);
    createNote(TENANT_B, Failure.NONE);
    enqueueOnly(TENANT_A, ExternalHandler.TYPE);
    enqueueOnly(TENANT_B, ExternalHandler.TYPE);

    processor.processTenant(TENANT_A.tenant()).block();

    assertThat(db.workItems())
        .filteredOn(row ->
            row.tenant().equals("tenant-a") && row.type().equals(FollowUpHandler.TYPE.value()))
        .allSatisfy(row -> assertThat(row.status()).isEqualTo("SUCCEEDED"));
    assertThat(db.workItems())
        .filteredOn(row -> row.tenant().equals("tenant-b"))
        .allSatisfy(row -> assertThat(row.status()).isEqualTo("PENDING"));
    assertThat(followUp.invocations())
        .hasSize(2)
        .allSatisfy(invocation -> {
          assertThat(invocation.itemTenant()).isEqualTo("tenant-a");
          assertThat(invocation.scope()).isEqualTo(ServiceIdentity.backendScope(TENANT_A.tenant()));
        });

    drain();

    assertThat(followUp.invocations())
        .hasSize(4)
        .allSatisfy(invocation ->
            assertThat(invocation.scope().tenant().value()).isEqualTo(invocation.itemTenant()));
    assertThat(terminalFailures(TENANT_A))
        .singleElement()
        .satisfies(item -> assertThat(item.tenant()).isEqualTo(TENANT_A.tenant()));
    assertThat(terminalFailures(TENANT_B))
        .singleElement()
        .satisfies(item -> assertThat(item.tenant()).isEqualTo(TENANT_B.tenant()));
    StepVerifier.create(failedWork.listTerminalFailures(10))
        .expectError(MissingScopeException.class)
        .verify();
  }

  @Test
  void oneTenantsProcessingFailureDoesNotStopTheOtherTenants(CapturedOutput output) {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_B, Failure.NONE);
    WorkProcessor isolating =
        new WorkProcessor(
            transactions,
            new FailingForTenant(repository, TENANT_A.tenant()),
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            policy,
            "isolating-processor");

    assertThat(isolating.runOnce().block()).isEqualTo(1L);

    assertThat(db.workItems())
        .filteredOn(row -> row.tenant().equals("tenant-b"))
        .singleElement()
        .satisfies(row -> assertThat(row.status()).isEqualTo("SUCCEEDED"));
    assertThat(db.workItems())
        .filteredOn(row -> row.tenant().equals("tenant-a"))
        .singleElement()
        .satisfies(row -> assertThat(row.status()).isEqualTo("PENDING"));
    assertThat(output.getAll())
        .contains("Processing work for tenant tenant-a failed: IllegalStateException")
        .doesNotContain("fixture: tenant-level fault");
  }

  @Test
  void tenantsAreDiscoveredByTheirLongestWaitingDueItem() {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_B, Failure.NONE);
    db.runSql(
        "update jobs.work_item set next_attempt_at = now() - interval '1 second'"
            + " where tenant_id = 'tenant-a'");
    db.runSql(
        "update jobs.work_item set next_attempt_at = now() - interval '1 minute'"
            + " where tenant_id = 'tenant-b'");

    assertThat(
            repository
                .tenantsWithDueWork(1, registry.types(), policy.stepTimeout())
                .collectList()
                .block())
        .as("a bounded wake-up reaches the tenant that waited longest, not the lowest id")
        .containsExactly(TENANT_B.tenant());
    assertThat(
            repository
                .tenantsWithDueWork(2, registry.types(), policy.stepTimeout())
                .collectList()
                .block())
        .containsExactly(TENANT_B.tenant(), TENANT_A.tenant());
  }

  @Test
  void anExpiredLeaseCountsAsWaitingSinceItsLeaseRanOut() {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_B, Failure.NONE);
    db.runSql(
        "update jobs.work_item set status = 'RUNNING', lease_token = gen_random_uuid(),"
            + " lease_owner = 'gone', lease_expires_at = now() - interval '2 minutes',"
            + " next_attempt_at = now() - interval '1 second', attempt_count = 1"
            + " where tenant_id = 'tenant-a'");
    db.runSql(
        "update jobs.work_item set next_attempt_at = now() - interval '1 minute'"
            + " where tenant_id = 'tenant-b'");

    assertThat(
            repository
                .tenantsWithDueWork(1, registry.types(), policy.stepTimeout())
                .collectList()
                .block())
        .as("a reclaimable lease waits from its expiry, not from its original due time")
        .containsExactly(TENANT_A.tenant());
  }

  @Test
  void theExhaustedLeaseSweepTouchesOnlyTheBoundTenant() {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_B, Failure.NONE);
    db.runSql(
        "update jobs.work_item set status = 'RUNNING', lease_token = gen_random_uuid(),"
            + " lease_owner = 'gone', lease_expires_at = now() - interval '1 minute',"
            + " attempt_count = max_attempts");

    processor.processTenant(TENANT_A.tenant()).block();

    assertThat(db.workItems())
        .filteredOn(row -> row.tenant().equals("tenant-a"))
        .singleElement()
        .satisfies(row -> {
          assertThat(row.status()).isEqualTo("FAILED");
          assertThat(row.reason()).isEqualTo("lease-expired-attempts-exhausted");
          assertThat(row.leaseToken()).isNull();
        });
    assertThat(db.workItems())
        .filteredOn(row -> row.tenant().equals("tenant-b"))
        .singleElement()
        .satisfies(row -> {
          assertThat(row.status())
              .as("another tenant's exhausted lease is untouched")
              .isEqualTo("RUNNING");
          assertThat(row.reason()).isNull();
          assertThat(row.leaseToken()).isNotNull();
        });
    assertThat(followUp.invocations()).isEmpty();
  }

  @Test
  void aDenyWriteFromAnExpiredLeaseIsRejected() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    WorkProcessor lateDenial =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) ->
                db.expireLeaseAsync(item.id()).thenReturn(DispatchDecision.DENY),
            singleItemPolicy(),
            "late-denial-processor");

    lateDenial.processTenant(TENANT_A.tenant()).block();

    WorkRow stale = db.work(itemId);
    assertThat(stale.status()).as("the fenced deny write changed nothing").isEqualTo("RUNNING");
    assertThat(stale.attempts()).isEqualTo(1);
    assertThat(stale.reason()).isNull();
    assertThat(stale.finishedAt()).isNull();
    assertThat(followUp.invocations()).isEmpty();

    processor.runOnce().block();
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
  }

  @Test
  void aLeaseTokenExistsOnlyWhileRunningAndSuccessClearsAnEarlierReason() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behaveOnce(item -> Mono.error(new IllegalStateException("first attempt fails")));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();
    WorkRow retried = db.work(itemId);
    assertThat(retried.status()).isEqualTo("PENDING");
    assertThat(retried.reason()).isEqualTo("IllegalStateException");
    assertThat(retried.leaseToken()).as("no fencing token outside RUNNING").isNull();
    assertThat(retried.leaseOwner()).as("the last lease stays on record").isNotNull();

    awaitAttempt(itemId, 2);
    WorkRow done = db.work(itemId);
    assertThat(done.status()).isEqualTo("SUCCEEDED");
    assertThat(done.reason()).as("no stale reason from an earlier attempt").isNull();
    assertThat(done.leaseToken()).isNull();
    assertThat(done.leaseExpiresAt()).isNotNull();

    assertThatThrownBy(() ->
            db.runSql(
                "update jobs.work_item set lease_token = gen_random_uuid() where id = '"
                    + itemId
                    + "'"))
        .as("the database refuses a token on a row that is not RUNNING")
        .isInstanceOf(DataIntegrityViolationException.class);
  }

  @Test
  void undecodableRowsAreFailedTerminallyAndTheSameBatchMovesPastThem(CapturedOutput output) {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_A, Failure.NONE);
    List<UUID> poison = List.of(db.workItems().get(0).id(), db.workItems().get(1).id());
    UUID healthy = db.workItems().get(2).id();
    for (int i = 0; i < poison.size(); i++) {
      db.runSql(
          "update jobs.work_item set payload = '{\"noteId\": {\"nested\": true}}'::jsonb,"
              + " next_attempt_at = now() - interval '"
              + (2 - i)
              + " minutes' where id = '"
              + poison.get(i)
              + "'");
    }

    assertThat(processor.processTenant(TENANT_A.tenant()).block())
        .as("one wake-up: two poison rows skipped, the valid item behind them dispatched")
        .isEqualTo(1L);

    for (UUID id : poison) {
      WorkRow failed = db.work(id);
      assertThat(failed.status()).isEqualTo("FAILED");
      assertThat(failed.attempts()).isEqualTo(1);
      assertThat(failed.reason()).isEqualTo("undecodable-work-item");
      assertThat(failed.finishedAt()).isNotNull();
      assertThat(failed.leaseToken()).isNull();
    }
    assertThat(output.getAll()).contains("cannot be decoded and is failed terminally");
    assertThat(db.work(healthy).status())
        .as("the queue moved past the poison rows within the same batch")
        .isEqualTo("SUCCEEDED");
    assertThat(followUp.invocations())
        .singleElement()
        .extracting(FollowUpHandler.Invocation::itemId)
        .isEqualTo(healthy);
    assertThat(terminalFailures(TENANT_A))
        .extracting(FailedWorkItem::id)
        .containsExactlyInAnyOrderElementsOf(poison);
    assertThat(terminalFailures(TENANT_A))
        .allSatisfy(item -> assertThat(item.safeReason()).contains("undecodable-work-item"));
  }

  @Test
  void aNonRetryableFailureIsTerminalOnTheAttemptThatRaisedIt() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    followUp.behave(item -> Mono.error(new NonRetryableWorkException("the note is gone")));

    singleItemProcessor().processTenant(TENANT_A.tenant()).block();

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("FAILED");
    assertThat(row.attempts()).as("two attempts were still permitted").isEqualTo(1);
    assertThat(row.maxAttempts()).isEqualTo(3);
    assertThat(row.reason()).isEqualTo("NonRetryableWorkException");
    assertThat(row.finishedAt()).isNotNull();
    assertThat(terminalFailures(TENANT_A))
        .singleElement()
        .satisfies(item -> assertThat(item.status()).isEqualTo(WorkStatus.FAILED));
    processor.runOnce().block();
    assertThat(followUp.invocations()).hasSize(1);
  }

  @Test
  void theHandlerDeadlineCountsFromTheClaimAndBoundsTheRecheckToo() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    RetryPolicy halfSecondDeadline =
        new RetryPolicy(
            policy.maxAttempts(),
            policy.backoffBase(),
            policy.backoffCap(),
            Duration.ofSeconds(5),
            1,
            Duration.ofMillis(500));
    followUp.behave(item -> Mono.delay(Duration.ofMillis(450)).then(followUp.applyEffect(item)));
    WorkProcessor slowRecheck =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) ->
                Mono.delay(Duration.ofMillis(150)).thenReturn(DispatchDecision.ALLOW),
            halfSecondDeadline,
            "slow-recheck-processor");

    slowRecheck.processTenant(TENANT_A.tenant()).block(Duration.ofSeconds(10));

    WorkRow overrun = db.work(itemId);
    assertThat(overrun.status()).isEqualTo("PENDING");
    assertThat(overrun.attempts()).isEqualTo(1);
    assertThat(overrun.reason())
        .as("150 ms recheck + 450 ms handler passes a 500 ms deadline measured from the claim")
        .isEqualTo("handler-deadline-exceeded");
    assertThat(followUp.invocations()).hasSize(1);

    followUp.reset();
    WorkProcessor silentRecheck =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) -> Mono.never(),
            halfSecondDeadline,
            "silent-recheck-processor");
    db.runSql("update jobs.work_item set next_attempt_at = now() where id = '" + itemId + "'");

    silentRecheck.processTenant(TENANT_A.tenant()).block(Duration.ofSeconds(10));

    WorkRow blocked = db.work(itemId);
    assertThat(blocked.status()).isEqualTo("PENDING");
    assertThat(blocked.attempts())
        .as("a recheck that never answers does not use an attempt")
        .isEqualTo(1);
    assertThat(blocked.reason()).isEqualTo("authorization-undecided");
    assertThat(followUp.invocations()).isEmpty();
  }

  // --- helpers -----------------------------------------------------------------------------

  /** A 5 s lease with a 0.5 s handler deadline: ample margin for the rollback and failure write. */
  private WorkProcessor shortDeadlineProcessor() {
    return new WorkProcessor(
        transactions,
        repository,
        registry,
        new TenantInternalOnlyDispatchAuthorization(),
        new RetryPolicy(
            policy.maxAttempts(),
            policy.backoffBase(),
            policy.backoffCap(),
            Duration.ofSeconds(5),
            10,
            Duration.ofMillis(500)),
        "short-deadline-processor");
  }

  private WorkProcessor lateClaimProcessor(Duration answerDelay, RetryPolicy retryPolicy) {
    return new WorkProcessor(
        transactions,
        new LateClaimAnswer(repository, answerDelay),
        registry,
        new TenantInternalOnlyDispatchAuthorization(),
        retryPolicy,
        "late-claim-processor");
  }

  private ClaimedWork claimOne(String owner) {
    return (ClaimedWork)
        transactions
            .inTransaction(scope ->
                repository
                    .claim(1, policy.leaseDuration(), owner, UUID.randomUUID(), registry.types())
                    .next())
            .contextWrite(Scopes.bind(ServiceIdentity.backendScope(TENANT_A.tenant())))
            .block();
  }

  /** Statements of other sessions that wait for a lock and name the work table. */
  private long statementsWaitingForTheWorkTable() {
    return db.count(
        "select count(*) from pg_stat_activity where wait_event_type = 'Lock'"
            + " and pid <> pg_backend_pid() and query like '%jobs.work_item%'"
            + " and query not like 'lock table%'");
  }

  /** Delegates everything, but each claim answers only after {@code delay}. */
  private static final class LateClaimAnswer extends DelegatingWorkRepository {
    private final Duration delay;

    private LateClaimAnswer(WorkRepository delegate, Duration delay) {
      super(delegate);
      this.delay = delay;
    }

    @Override
    public Flux<Claim> claim(
        int limit, Duration lease, String leaseOwner, UUID leaseToken, Set<WorkType> types) {
      return super.claim(limit, lease, leaseOwner, leaseToken, types)
          .collectList()
          .delayElement(delay)
          .flatMapMany(Flux::fromIterable);
    }
  }

  /**
   * Delegates everything, but the claim commits in a transaction of its own and its answer never
   * reaches the caller, as when the connection stalls after the commit was applied.
   */
  private final class ClaimAnswerLost extends DelegatingWorkRepository {
    private final CompletableFuture<Void> committed = new CompletableFuture<>();

    private ClaimAnswerLost(WorkRepository delegate) {
      super(delegate);
    }

    CompletableFuture<Void> committed() {
      return committed;
    }

    @Override
    public Flux<Claim> claim(
        int limit, Duration lease, String leaseOwner, UUID leaseToken, Set<WorkType> types) {
      return Scopes.current()
          .flatMapMany(scope ->
              transactions
                  .inTransaction(
                      own -> super.claim(limit, lease, leaseOwner, leaseToken, types).collectList())
                  .contextWrite(Scopes.bind(scope))
                  // Drops the caller's transaction from the context: this one commits by itself.
                  .contextWrite(context -> Context.empty())
                  .doOnSuccess(claims -> committed.complete(null))
                  .thenMany(Flux.<Claim>never()));
    }
  }

  /** Delegates everything, but every completion write fails before it reaches the database. */
  private static final class FailingCompletion extends DelegatingWorkRepository {
    private FailingCompletion(WorkRepository delegate) {
      super(delegate);
    }

    @Override
    public Mono<Boolean> complete(UUID id, UUID leaseToken, EffectOutcome outcome) {
      return Mono.error(new IllegalStateException("fixture: the completion write failed"));
    }
  }

  /** Delegates everything, but fails the per-tenant expiry sweep for one tenant. */
  private static final class FailingForTenant extends DelegatingWorkRepository {
    private final TenantId failing;

    private FailingForTenant(WorkRepository delegate, TenantId failing) {
      super(delegate);
      this.failing = failing;
    }

    @Override
    public Mono<Long> failExhaustedExpiredLeases(String safeReason) {
      return Scopes.current()
          .flatMap(scope ->
              scope.tenant().equals(failing)
                  ? Mono.error(new IllegalStateException("fixture: tenant-level fault"))
                  : super.failExhaustedExpiredLeases(safeReason));
    }
  }

  /** Delegates everything, but holds each completion write until {@code release} completes. */
  private static final class CompletionHeldUntil extends DelegatingWorkRepository {
    private final CompletableFuture<Void> release;

    private CompletionHeldUntil(WorkRepository delegate, CompletableFuture<Void> release) {
      super(delegate);
      this.release = release;
    }

    @Override
    public Mono<Boolean> complete(UUID id, UUID leaseToken, EffectOutcome outcome) {
      return Mono.fromFuture(release).then(super.complete(id, leaseToken, outcome));
    }
  }

  private UUID createNote(ScopeContext scope, Failure failure) {
    return createNote(scope, failure, "note body");
  }

  private UUID createNote(ScopeContext scope, Failure failure, String body) {
    return notes.createWithFollowUp(body, failure).contextWrite(Scopes.bind(scope)).block();
  }

  private UUID enqueueOnly(ScopeContext scope, WorkType type) {
    return notes.enqueueOnly(type, Map.of()).contextWrite(Scopes.bind(scope)).block();
  }

  private long releaseCount(UUID itemId) {
    return db.count("select release_count from jobs.work_item where id = '" + itemId + "'");
  }

  private long giveBack(ScopeContext backend, UUID leaseToken) {
    return transactions
        .inTransaction(scope -> repository.giveBack(leaseToken, "dispatch-cancelled"))
        .contextWrite(Scopes.bind(backend))
        .block();
  }

  private List<FailedWorkItem> terminalFailures(ScopeContext scope) {
    return failedWork
        .listTerminalFailures(50)
        .contextWrite(Scopes.bind(scope))
        .collectList()
        .block();
  }

  private WorkProcessor independentProcessor(String owner) {
    return new WorkProcessor(
        transactions,
        repository,
        registry,
        new TenantInternalOnlyDispatchAuthorization(),
        policy,
        owner);
  }

  /** Dispatches one item per run, so state between a stale write and the reclaim is visible. */
  private WorkProcessor singleItemProcessor() {
    return new WorkProcessor(
        transactions,
        repository,
        registry,
        new TenantInternalOnlyDispatchAuthorization(),
        singleItemPolicy(),
        "single-item-processor");
  }

  /** Runs the processor until a wake-up dispatches nothing. */
  private void drain() {
    await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> assertThat(processor.runOnce().block()).isZero());
  }

  /** One claim per run: the retry becomes due by backoff, never by a same-run reclaim. */
  private void awaitAttempt(UUID itemId, int attempt) {
    WorkProcessor single = singleItemProcessor();
    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          single.processTenant(TENANT_A.tenant()).block();
          assertThat(db.work(itemId).attempts()).isEqualTo(attempt);
        });
  }

  private RetryPolicy singleItemPolicy() {
    return new RetryPolicy(
        policy.maxAttempts(), policy.backoffBase(), policy.backoffCap(), policy.leaseDuration(), 1);
  }

  private static Duration backoffOf(WorkRow row) {
    return Duration.between(row.updatedAt(), row.nextAttemptAt());
  }
}
