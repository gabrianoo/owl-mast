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
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkStatus;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.application.HandlerRegistry;
import com.aisquad.owlmast.jobs.application.TenantInternalOnlyDispatchAuthorization;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
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
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
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
  void aLeaseThatExpiresNaturallyWhileTheHandlerRunsCannotCommit() {
    createNote(TENANT_A, Failure.NONE);
    UUID itemId = db.workItems().get(0).id();
    String key = "owlmast-work:" + itemId;
    WorkProcessor shortLease =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofMillis(400), Duration.ofMillis(400), 1),
            "short-lease-processor");
    followUp.behaveOnce(
        item -> Mono.delay(Duration.ofMillis(900)).then(followUp.applyEffect(item)));

    shortLease.processTenant(TENANT_A.tenant()).block();

    WorkRow stale = db.work(itemId);
    assertThat(stale.status())
        .as("completion after natural expiry changes nothing")
        .isEqualTo("RUNNING");
    assertThat(stale.attempts()).isEqualTo(1);
    assertThat(stale.effectOutcome()).isNull();
    assertThat(stale.leaseExpiresAt()).isBefore(db.work(itemId).updatedAt().plusSeconds(1));

    processor.runOnce().block();

    WorkRow done = db.work(itemId);
    assertThat(done.status()).isEqualTo("SUCCEEDED");
    assertThat(done.attempts()).isEqualTo(2);
    assertThat(done.leaseOwner()).isEqualTo(processor.leaseOwner());
    assertThat(effects.received(key)).isEqualTo(2);
    assertThat(effects.applied(key)).isEqualTo(1);
  }

  @Test
  void itemsWaitingInABatchDoNotConsumeTheirLeases() {
    for (int i = 0; i < 5; i++) {
      createNote(TENANT_A, Failure.NONE);
    }
    WorkProcessor shortLease =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            new TenantInternalOnlyDispatchAuthorization(),
            new RetryPolicy(
                3, Duration.ofMillis(100), Duration.ofMillis(400), Duration.ofMillis(1000), 5),
            "batch-processor");
    followUp.behave(item -> Mono.delay(Duration.ofMillis(300)).then(followUp.applyEffect(item)));

    long dispatched = shortLease.processTenant(TENANT_A.tenant()).block();

    assertThat(dispatched).as("the whole batch took longer than one lease").isEqualTo(5);
    assertThat(db.workItems())
        .hasSize(5)
        .allSatisfy(row -> {
          assertThat(row.status()).isEqualTo("SUCCEEDED");
          assertThat(row.attempts()).as("no item lost its lease while waiting").isEqualTo(1);
          assertThat(Duration.between(row.leaseExpiresAt().minusSeconds(1), row.finishedAt()))
              .as("each lease started just before its own dispatch")
              .isLessThan(Duration.ofMillis(900));
        });
    assertThat(effects.totalReceived()).isEqualTo(5);
  }

  // --- AC5 ---------------------------------------------------------------------------------

  @Test
  void retriesPersistAttemptsCappedBackoffAndSafeReasonThenFailTerminally(CapturedOutput output) {
    createNote(TENANT_A, Failure.NONE, SECRET);
    UUID itemId = db.workItems().get(0).id();
    followUp.behave(item -> Mono.error(new IllegalStateException("handler saw " + SECRET)));

    processor.runOnce().block();
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
            policy,
            "undecided-processor");
    WorkProcessor silent =
        new WorkProcessor(
            transactions,
            repository,
            registry,
            (item, registration) -> Mono.just(DispatchDecision.UNDECIDED),
            policy,
            "silent-processor");

    undecided.processTenant(TENANT_A.tenant()).block();
    WorkRow blocked = db.work(itemId);
    assertThat(blocked.status()).isEqualTo("PENDING");
    assertThat(blocked.attempts()).isEqualTo(1);
    assertThat(blocked.reason()).isEqualTo("authorization-undecided");
    assertThat(followUp.invocations()).isEmpty();

    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          silent.processTenant(TENANT_A.tenant()).block();
          assertThat(db.work(itemId).attempts()).isEqualTo(2);
        });
    assertThat(followUp.invocations()).isEmpty();

    awaitAttempt(itemId, 3);
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
  }

  @Test
  void anUnregisteredWorkTypeIsRetriedWithASafeReason() {
    UUID itemId = enqueueOnly(TENANT_A, WorkType.of("fixture.unknown"));

    processor.runOnce().block();

    WorkRow row = db.work(itemId);
    assertThat(row.status()).isEqualTo("PENDING");
    assertThat(row.attempts()).isEqualTo(1);
    assertThat(row.reason()).isEqualTo("unregistered-work-type");
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

  // --- helpers -----------------------------------------------------------------------------

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
        new RetryPolicy(
            policy.maxAttempts(),
            policy.backoffBase(),
            policy.backoffCap(),
            policy.leaseDuration(),
            1),
        "single-item-processor");
  }

  /** Runs the processor until a wake-up dispatches nothing. */
  private void drain() {
    await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> assertThat(processor.runOnce().block()).isZero());
  }

  private void awaitAttempt(UUID itemId, int attempt) {
    await()
        .atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(50))
        .untilAsserted(() -> {
          processor.runOnce().block();
          assertThat(db.work(itemId).attempts()).isEqualTo(attempt);
        });
  }

  private static Duration backoffOf(WorkRow row) {
    return Duration.between(row.updatedAt(), row.nextAttemptAt());
  }
}
