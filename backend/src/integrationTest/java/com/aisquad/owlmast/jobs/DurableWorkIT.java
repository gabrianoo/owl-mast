package com.aisquad.owlmast.jobs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.awaitility.Awaitility.await;

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
import com.aisquad.owlmast.jobs.port.ClaimedWork;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import com.aisquad.owlmast.platform.scope.PrincipalId;
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
import java.util.concurrent.TimeUnit;
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
  void anUndecidedRecheckBlocksTheAttemptWithoutInvokingTheHandler() {
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
    assertThat(backoffOf(blocked)).isBetween(Duration.ofMillis(80), Duration.ofMillis(300));
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
    }
    assertThat(followUp.invocations()).isEmpty();

    awaitAttempt(itemId, 1);
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
    assertThat(db.work(itemId).reason()).isNull();
  }

  @Test
  void workThisInstanceCannotRunIsLeftForAnInstanceThatCan() {
    UUID unknownType = enqueueOnly(TENANT_A, WorkType.of("fixture.unknown"));
    UUID newerVersion = enqueueOnly(TENANT_A, FollowUpHandler.TYPE);
    db.runSql(
        "update jobs.work_item set contract_version = "
            + (WorkItemContract.VERSION + 1)
            + " where id = '"
            + newerVersion
            + "'");

    assertThat(repository.tenantsWithDueWork(10, registry.types()).collectList().block())
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

    assertThat(repository.tenantsWithDueWork(1, registry.types()).collectList().block())
        .as("a bounded wake-up reaches the tenant that waited longest, not the lowest id")
        .containsExactly(TENANT_B.tenant());
    assertThat(repository.tenantsWithDueWork(2, registry.types()).collectList().block())
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

    assertThat(repository.tenantsWithDueWork(1, registry.types()).collectList().block())
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
  void anUndecodableRowIsFailedTerminallyInsteadOfStallingTheTenantsQueue(CapturedOutput output) {
    createNote(TENANT_A, Failure.NONE);
    createNote(TENANT_A, Failure.NONE);
    UUID poison = db.workItems().get(0).id();
    UUID healthy = db.workItems().get(1).id();
    db.runSql(
        "update jobs.work_item set payload = '{\"noteId\": {\"nested\": true}}'::jsonb,"
            + " next_attempt_at = now() - interval '1 minute' where id = '"
            + poison
            + "'");

    processor.processTenant(TENANT_A.tenant()).block();
    WorkRow failed = db.work(poison);
    assertThat(failed.status()).isEqualTo("FAILED");
    assertThat(failed.attempts()).isEqualTo(1);
    assertThat(failed.reason()).isEqualTo("undecodable-work-item");
    assertThat(failed.finishedAt()).isNotNull();
    assertThat(failed.leaseToken()).isNull();
    assertThat(output.getAll()).contains("cannot be decoded and is failed terminally");

    processor.processTenant(TENANT_A.tenant()).block();
    assertThat(db.work(healthy).status())
        .as("the queue moved past the poison row")
        .isEqualTo("SUCCEEDED");
    assertThat(followUp.invocations())
        .singleElement()
        .extracting(FollowUpHandler.Invocation::itemId)
        .isEqualTo(healthy);
    assertThat(terminalFailures(TENANT_A))
        .singleElement()
        .satisfies(item -> {
          assertThat(item.id()).isEqualTo(poison);
          assertThat(item.safeReason()).contains("undecodable-work-item");
        });
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
    followUp.behave(item -> Mono.delay(Duration.ofMillis(300)).then(followUp.applyEffect(item)));
    WorkProcessor slowRecheck =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) ->
                Mono.delay(Duration.ofMillis(350)).thenReturn(DispatchDecision.ALLOW),
            halfSecondDeadline,
            "slow-recheck-processor");

    slowRecheck.processTenant(TENANT_A.tenant()).block(Duration.ofSeconds(10));

    WorkRow overrun = db.work(itemId);
    assertThat(overrun.status()).isEqualTo("PENDING");
    assertThat(overrun.attempts()).isEqualTo(1);
    assertThat(overrun.reason())
        .as("350 ms recheck + 300 ms handler passes a 500 ms deadline measured from the claim")
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

  /** Plain delegation, for fixtures that change one repository call. */
  private abstract static class DelegatingWorkRepository implements WorkRepository {
    private final WorkRepository delegate;

    DelegatingWorkRepository(WorkRepository delegate) {
      this.delegate = delegate;
    }

    @Override
    public Mono<Long> failExhaustedExpiredLeases(String safeReason) {
      return delegate.failExhaustedExpiredLeases(safeReason);
    }

    @Override
    public Mono<Void> limitStatementTime(Duration timeout) {
      return delegate.limitStatementTime(timeout);
    }

    @Override
    public Mono<UUID> insert(
        UUID id,
        EnqueueRequest request,
        int contractVersion,
        int maxAttempts,
        PrincipalId enqueuedBy) {
      return delegate.insert(id, request, contractVersion, maxAttempts, enqueuedBy);
    }

    @Override
    public Flux<ClaimedWork> claim(
        int limit, Duration lease, String leaseOwner, Set<WorkType> types) {
      return delegate.claim(limit, lease, leaseOwner, types);
    }

    @Override
    public Mono<Boolean> release(UUID id, UUID leaseToken, String safeReason, Duration backoff) {
      return delegate.release(id, leaseToken, safeReason, backoff);
    }

    @Override
    public Mono<Boolean> complete(UUID id, UUID leaseToken, EffectOutcome outcome) {
      return delegate.complete(id, leaseToken, outcome);
    }

    @Override
    public Mono<Boolean> fail(
        UUID id, UUID leaseToken, String safeReason, Duration backoff, boolean terminal) {
      return delegate.fail(id, leaseToken, safeReason, backoff, terminal);
    }

    @Override
    public Mono<Boolean> deny(UUID id, UUID leaseToken, String safeReason) {
      return delegate.deny(id, leaseToken, safeReason);
    }

    @Override
    public Flux<TenantId> tenantsWithDueWork(int limit, Set<WorkType> types) {
      return delegate.tenantsWithDueWork(limit, types);
    }

    @Override
    public Flux<FailedWorkItem> listTerminalFailures(int limit) {
      return delegate.listTerminalFailures(limit);
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
