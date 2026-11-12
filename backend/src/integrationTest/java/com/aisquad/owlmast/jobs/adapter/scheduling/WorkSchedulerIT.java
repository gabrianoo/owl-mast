package com.aisquad.owlmast.jobs.adapter.scheduling;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import com.aisquad.owlmast.fixtures.jobs.HeldWorkRepository;
import com.aisquad.owlmast.fixtures.jobs.HeldWorkRepository.Call;
import com.aisquad.owlmast.fixtures.notes.DbProbe;
import com.aisquad.owlmast.fixtures.notes.DbProbe.WorkRow;
import com.aisquad.owlmast.fixtures.notes.EffectStore;
import com.aisquad.owlmast.fixtures.notes.FollowUpHandler;
import com.aisquad.owlmast.fixtures.notes.NotesFixture;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.Failure;
import com.aisquad.owlmast.fixtures.notes.NotesFixtureConfiguration;
import com.aisquad.owlmast.jobs.application.HandlerRegistry;
import com.aisquad.owlmast.jobs.application.TenantInternalGrants;
import com.aisquad.owlmast.jobs.application.TenantInternalOnlyDispatchAuthorization;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
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
import reactor.core.Disposable;
import reactor.core.publisher.Mono;

/**
 * The scheduler's graceful stop, step by step: the stop ends the wake-up in flight, completes only
 * when the give-back of the cancelled dispatch has ended, and no later wake-up claims work. The
 * context's own scheduler is off; the test drives a scheduler of its own.
 */
@SpringBootTest(
    properties = {"owlmast.jobs.scheduler.enabled=false", "owlmast.jobs.lease-duration=PT30S"})
@Import({
  ContainersConfiguration.class,
  StubIdentityConfiguration.class,
  NotesFixtureConfiguration.class
})
@ExtendWith(OutputCaptureExtension.class)
class WorkSchedulerIT {

  private static final ScopeContext TENANT_A = ScopeContext.of("tenant-a", "person-a");

  @Autowired private NotesFixture notes;
  @Autowired private TenantInternalGrants grants;
  @Autowired private FollowUpHandler followUp;
  @Autowired private EffectStore effects;
  @Autowired private DbProbe db;
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

  @Test
  void stopWaitsForTheGiveBackAndLaterWakeUpsClaimNothing() {
    notes.createWithFollowUp("note body", Failure.NONE).contextWrite(Scopes.bind(TENANT_A)).block();
    UUID itemId = db.workItems().get(0).id();
    CompletableFuture<Void> handlerStarted = new CompletableFuture<>();
    followUp.behaveOnce(item -> {
      handlerStarted.complete(null);
      return Mono.never();
    });
    HeldWorkRepository heldGiveBack = new HeldWorkRepository(repository, Call.GIVE_BACK);
    WorkScheduler scheduler =
        new WorkScheduler(
            new WorkProcessor(
                transactions,
                heldGiveBack,
                registry,
                new TenantInternalOnlyDispatchAuthorization(grants),
                policy,
                "scheduler-test-processor"),
            () -> Mono.just(true));

    assertThat(scheduler.isRunning()).isFalse();
    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(heldGiveBack.claims())
        .as("a scheduler that was not started claims nothing")
        .isZero();

    scheduler.start();
    Disposable wakeUp = scheduler.wake().subscribe();
    handlerStarted.orTimeout(10, TimeUnit.SECONDS).join();
    int claimsBeforeStop = heldGiveBack.claims();

    AtomicBoolean stopped = new AtomicBoolean();
    scheduler.stop(() -> stopped.set(true));

    heldGiveBack.entered().orTimeout(10, TimeUnit.SECONDS).join();
    await().atMost(Duration.ofSeconds(10)).until(wakeUp::isDisposed);
    assertThat(scheduler.isRunning()).isFalse();
    assertThat(stopped)
        .as("the stop is not complete while the give-back is still in flight")
        .isFalse();
    assertThat(db.work(itemId).status()).isEqualTo("RUNNING");

    heldGiveBack.release();
    await().atMost(Duration.ofSeconds(10)).untilTrue(stopped);
    WorkRow givenBack = db.work(itemId);
    assertThat(givenBack.status())
        .as("the give-back was written before the stop completed")
        .isEqualTo("PENDING");
    assertThat(givenBack.attempts()).isZero();

    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(heldGiveBack.claims())
        .as("the item is due again, but a stopped scheduler claims nothing")
        .isEqualTo(claimsBeforeStop);
    assertThat(db.work(itemId).status()).isEqualTo("PENDING");

    scheduler.start();
    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(db.work(itemId).status())
        .as("a restarted scheduler runs wake-ups again")
        .isEqualTo("SUCCEEDED");
  }

  /**
   * E01-R-06 (retro B5): readiness DOWN on an unsupported PostgreSQL does not stop a scheduled
   * task, so the wake-up refuses by itself while the database is not confirmed as supported and
   * logs the refusal when it starts. Review 5883535263: a yes is not kept, because the server
   * behind the same address can change (a failover to an older server), and a precondition read
   * that hangs counts as no.
   */
  @Test
  void noWorkIsClaimedWhileTheDatabaseServerIsNotConfirmedAsSupported(CapturedOutput output) {
    notes.createWithFollowUp("note body", Failure.NONE).contextWrite(Scopes.bind(TENANT_A)).block();
    UUID itemId = db.workItems().get(0).id();
    AtomicReference<Mono<Boolean>> answer = new AtomicReference<>(Mono.just(false));
    AtomicInteger asked = new AtomicInteger();
    WorkScheduler scheduler =
        new WorkScheduler(
            new WorkProcessor(
                transactions,
                repository,
                registry,
                new TenantInternalOnlyDispatchAuthorization(grants),
                policy,
                "precondition-test-processor"),
            () -> {
              asked.incrementAndGet();
              return answer.get();
            },
            Duration.ofMillis(200));
    scheduler.start();

    scheduler.wake().block(Duration.ofSeconds(10));
    answer.set(Mono.empty());
    scheduler.wake().block(Duration.ofSeconds(10));
    answer.set(Mono.error(new IllegalStateException("s3cr3t connection detail")));
    scheduler.wake().block(Duration.ofSeconds(10));
    answer.set(Mono.never());
    scheduler.wake().block(Duration.ofSeconds(10));

    assertThat(db.work(itemId).status())
        .as("unsupported, unknown, unreadable and unanswered all leave the work unclaimed")
        .isEqualTo("PENDING");
    assertThat(db.work(itemId).attempts()).isZero();
    assertThat(asked).hasValue(4);
    assertThat(output.getAll().split("Durable work is not started", -1))
        .as("the refusal is logged once, not at every wake-up")
        .hasSize(2);
    assertThat(output.getAll()).doesNotContain("s3cr3t");

    answer.set(Mono.just(true));
    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(db.work(itemId).status()).isEqualTo("SUCCEEDED");
    assertThat(output.getAll()).contains("Durable work resumes");

    notes
        .createWithFollowUp("second note", Failure.NONE)
        .contextWrite(Scopes.bind(TENANT_A))
        .block();
    UUID second =
        db.workItems().stream()
            .filter(row -> !row.id().equals(itemId))
            .findFirst()
            .orElseThrow()
            .id();
    answer.set(Mono.just(false));
    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(asked).as("a confirmed server is asked again at the next wake-up").hasValue(6);
    assertThat(db.work(second).status())
        .as("after the server stops answering as supported, nothing more is claimed")
        .isEqualTo("PENDING");
    assertThat(output.getAll().split("Durable work is not started", -1))
        .as("the new refusal is logged again")
        .hasSize(3);
    scheduler.stop();
  }

  /**
   * Review 5883535263: the production wiring of the precondition. The bean SchedulingConfiguration
   * registers asks the bootstrap feature's schema baseline: a PostgreSQL 16 server and a missing
   * baseline leave the work unclaimed, a PostgreSQL 17 server lets the wake-up run.
   */
  @Test
  void theRegisteredSchedulerRunsOnlyOnASupportedServerFromTheSchemaBaseline() {
    notes.createWithFollowUp("note body", Failure.NONE).contextWrite(Scopes.bind(TENANT_A)).block();
    UUID itemId = db.workItems().get(0).id();
    AtomicReference<Mono<SchemaBaseline>> baseline =
        new AtomicReference<>(Mono.just(baselineOn(160_011)));
    WorkScheduler scheduler =
        new SchedulingConfiguration()
            .workScheduler(
                new WorkProcessor(
                    transactions,
                    repository,
                    registry,
                    new TenantInternalOnlyDispatchAuthorization(grants),
                    policy,
                    "wiring-test-processor"),
                () -> baseline.get());
    scheduler.start();

    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(db.work(itemId).status()).as("PostgreSQL 16").isEqualTo("PENDING");
    baseline.set(Mono.empty());
    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(db.work(itemId).status()).as("no baseline").isEqualTo("PENDING");
    assertThat(db.work(itemId).attempts()).isZero();

    baseline.set(Mono.just(baselineOn(170_000)));
    scheduler.wake().block(Duration.ofSeconds(10));
    assertThat(db.work(itemId).status()).as("PostgreSQL 17").isEqualTo("SUCCEEDED");
    scheduler.stop();
  }

  private static SchemaBaseline baselineOn(int serverVersionNumber) {
    return new SchemaBaseline("1.1.1", "0.8.2", Instant.EPOCH, serverVersionNumber);
  }

  /** Review 5883535263: a stop ends a precondition read that has not answered. */
  @Test
  void aStopEndsAPreconditionReadInFlight() {
    WorkScheduler scheduler =
        new WorkScheduler(
            new WorkProcessor(
                transactions,
                repository,
                registry,
                new TenantInternalOnlyDispatchAuthorization(grants),
                policy,
                "precondition-stop-processor"),
            Mono::never,
            Duration.ofMinutes(5));
    scheduler.start();
    Disposable wakeUp = scheduler.wake().subscribe();
    scheduler.stop();
    await().atMost(Duration.ofSeconds(5)).until(wakeUp::isDisposed);
  }
}
