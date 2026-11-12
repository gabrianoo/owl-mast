package com.aisquad.owlmast.jobs.adapter.scheduling;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

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
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
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
class WorkSchedulerIT {

  private static final ScopeContext TENANT_A = ScopeContext.of("tenant-a", "person-a");

  @Autowired private NotesFixture notes;
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
                new TenantInternalOnlyDispatchAuthorization(),
                policy,
                "scheduler-test-processor"));

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
}
