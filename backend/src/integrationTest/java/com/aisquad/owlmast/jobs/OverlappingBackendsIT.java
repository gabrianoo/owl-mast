package com.aisquad.owlmast.jobs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.fixtures.restart.FixtureProcesses;
import com.aisquad.owlmast.fixtures.restart.RestartFixtureProcess;
import com.aisquad.owlmast.testing.OwlMastPostgres;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * Two backends on one database at the same time. The chart runs one backend and replaces it with
 * {@code Recreate}, but a pod that is deleted or evicted outside a rollout is replaced while it may
 * still be shutting down, so for a while two application processes share the database. Each test
 * runs two genuinely separate JVMs with the real application against one PostgreSQL and observes
 * the database over JDBC from the test JVM, which runs no application context of its own:
 *
 * <ul>
 *   <li>both start on an empty database at once, so both run Flyway on it, and then both work on
 *       one queue;
 *   <li>one is asked to stop (SIGTERM) while it holds an item and the other is running. Its handler
 *       is waiting, with no statement in flight and nothing written in its transaction;
 *   <li>one finishes its attempt only after its lease expired and the other completed the item. The
 *       test sets the lease to the past: a running backend cancels a handler at its deadline,
 *       before the lease ends, so on its own this happens only to a process that was paused or
 *       stalled past its lease.
 * </ul>
 *
 * <p>The follow-up handler's effect is a row per invocation in {@value
 * RestartFixtureProcess#EFFECT_LOG_TABLE}, written outside the handler's transaction, so the tests
 * count raw deliveries across both processes. Additional tests use a durable unique-key receiver,
 * SIGSTOP/SIGCONT across real lease expiry, and shutdown during a statement. These are process
 * tests with Testcontainers, not Kubernetes tests. A process killed while it holds a lease is
 * covered by {@link ProcessRestartRecoveryIT}.
 */
class OverlappingBackendsIT {

  private static final Duration LONG_LEASE = Duration.ofMinutes(5);
  private static final Duration STARTUP = Duration.ofMinutes(3);
  private static final String OWNER_PREFIX = "owl-mast-backend/";

  /** Filled by a trigger the queue test installs: one row per claim of a work item. */
  private static final String CLAIM_LOG_TABLE = "overlap_probe.claim_log";

  private static final int SEEDED_WORK_ITEMS =
      RestartFixtureProcess.SEEDED_FOLLOW_UPS + RestartFixtureProcess.SEEDED_MUTATIONS;
  private PostgreSQLContainer database;
  private FixtureProcesses processes;

  /** A fresh, empty database per test: the first test needs one that was never migrated. */
  @BeforeEach
  void startDatabase() throws IOException {
    database = OwlMastPostgres.vectorChord();
    database.start();
    processes = new FixtureProcesses(Path.of("build", "overlap-processes"));
  }

  @AfterEach
  void stopEverything() {
    if (processes != null) {
      processes.stopAll();
    }
    if (database != null) {
      database.stop();
    }
  }

  /** One {@code jobs.work_item} row as seen over JDBC. */
  private record Lease(UUID id, String status, String owner, UUID token, int attempts) {}

  /** One row of the effect log: which instance applied the effect, on which attempt. */
  private record Effect(String instance, int attempt) {}

  @Test
  void twoBackendsStartedTogetherMigrateOnceAndRunEachItemOfOneQueueOnce(@TempDir Path signals)
      throws Exception {
    int migrations =
        new PathMatchingResourcePatternResolver()
            .getResources("classpath:db/migration/V*.sql")
            .length;
    assertThat(migrations)
        .as("the application's own migrations are on the class path")
        .isPositive();
    int extraFollowUps = 30;
    int followUps = RestartFixtureProcess.SEEDED_FOLLOW_UPS + extraFollowUps;
    Path seedSignal = signals.resolve("seed");
    Process first;
    Process second;

    // An open transaction that created the schema of the first migration: whichever process runs
    // that migration waits for this transaction inside it, holding Flyway's lock, so both
    // processes are provably in their migration phase at the same time. Flyway takes the lock once
    // per migration, so after this one either process may apply any of the later ones.
    try (Connection blocker = database.createConnection("");
        Statement statement = blocker.createStatement()) {
      blocker.setAutoCommit(false);
      statement.execute("create schema bootstrap");
      long blockerPid = scalar(statement, "select pg_backend_pid()");

      first =
          launch(
              "together-first",
              Duration.ofSeconds(30),
              "first",
              RestartFixtureProcess.MODE_SLOW,
              RestartFixtureProcess.EFFECT_LOG,
              RestartFixtureProcess.SEED,
              RestartFixtureProcess.EXTRA_FOLLOW_UPS + extraFollowUps,
              RestartFixtureProcess.SEED_AFTER + seedSignal);
      second =
          launch(
              "together-second",
              Duration.ofSeconds(30),
              "second",
              RestartFixtureProcess.MODE_SLOW,
              RestartFixtureProcess.EFFECT_LOG);

      // Flyway holds its lock on one connection and runs the migration on another, and it asks
      // for the lock with pg_try_advisory_xact_lock once a second, at most 51 times (one try and
      // 50 retries, the defaults of Flyway 12.4.0). So a process that is refused shows up as a
      // session whose last statement is that call, not as a waiter.
      String lockHolders =
          "select held.pid from pg_locks held where held.locktype = 'advisory' and held.granted";
      await()
          .atMost(STARTUP)
          .pollInterval(Duration.ofMillis(100))
          .ignoreExceptions()
          .untilAsserted(() -> {
            assertBothAlive(first, second, "together-first", "together-second");
            assertThat(count("select count(*) from (" + lockHolders + ") as holder"))
                .as(() -> "one session holds Flyway's advisory lock; sessions: " + sessions())
                .isEqualTo(1);
            assertThat(
                    count(
                        "select count(*) from pg_stat_activity stuck where "
                            + blockerPid
                            + " = any (pg_blocking_pids(stuck.pid))"))
                .as(() -> "one session waits inside the first migration; sessions: " + sessions())
                .isEqualTo(1);
            assertThat(
                    count(
                        "select count(*) from pg_stat_activity refused"
                            + " where refused.pid <> pg_backend_pid()"
                            + " and refused.query like '%pg_try_advisory%'"
                            + " and refused.pid not in ("
                            + lockHolders
                            + ")"))
                .as(() ->
                    "the other process asked for the lock and was refused; sessions: " + sessions())
                .isEqualTo(1);
          });
      assertThat(count("select count(*) from flyway_schema_history"))
          .as("no migration is recorded while the first one is held")
          .isZero();
      blocker.rollback();
    }

    await()
        .atMost(STARTUP)
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
          assertBothAlive(first, second, "together-first", "together-second");
          assertThat(processes.log("together-first")).contains(RestartFixtureProcess.STARTED);
          assertThat(processes.log("together-second")).contains(RestartFixtureProcess.STARTED);
        });
    assertThat(count("select count(*) from flyway_schema_history where success"))
        .as("every migration is recorded once, although two processes ran Flyway")
        .isEqualTo(migrations);
    assertThat(count("select count(*) from flyway_schema_history")).isEqualTo(migrations);
    assertThat(count("select count(distinct version) from flyway_schema_history"))
        .isEqualTo(migrations);

    // Both are up and polling an empty queue. A claim adds one to attempt_count, but a release and
    // a give-back take it away again, so the finished row cannot show a second claim. This trigger
    // records every claim (a row that becomes RUNNING under a new lease token) from here on.
    assertThat(count("select count(*) from jobs.work_item")).as("nothing is queued yet").isZero();
    execute("create schema overlap_probe");
    execute(
        "create table "
            + CLAIM_LOG_TABLE
            + " (item_id uuid not null, work_type text not null, lease_owner text not null)");
    execute(
        "create function overlap_probe.log_claim() returns trigger language plpgsql as $$ begin"
            + " insert into "
            + CLAIM_LOG_TABLE
            + " values (new.id, new.work_type, new.lease_owner); return new; end $$");
    execute(
        "create trigger overlap_probe_log_claim after update on jobs.work_item for each row"
            + " when (new.status = 'RUNNING' and new.lease_token is distinct from old.lease_token)"
            + " execute function overlap_probe.log_claim()");

    // Now the first one fills the queue.
    Files.createFile(seedSignal);
    int workItems = followUps + RestartFixtureProcess.SEEDED_MUTATIONS;
    await()
        .atMost(Duration.ofMinutes(2))
        .pollInterval(Duration.ofMillis(250))
        .ignoreExceptions()
        .untilAsserted(() -> {
          assertBothAlive(first, second, "together-first", "together-second");
          assertThat(count("select count(*) from jobs.work_item where status = 'SUCCEEDED'"))
              .isEqualTo(workItems);
          assertThat(
                  count("select count(*) from audit.publication_intent where published_at is null"))
              .isZero();
        });

    assertThat(count("select count(*) from jobs.work_item")).isEqualTo(workItems);
    assertThat(count("select count(*) from jobs.work_item where attempt_count <> 1"))
        .as("no item has a second counted attempt")
        .isZero();
    assertThat(count("select count(*) from " + CLAIM_LOG_TABLE))
        .as("every item was claimed once, counted or not, across both processes")
        .isEqualTo(workItems);
    assertThat(count("select count(distinct item_id) from " + CLAIM_LOG_TABLE))
        .isEqualTo(workItems);
    assertThat(count("select count(*) from " + RestartFixtureProcess.EFFECT_LOG_TABLE))
        .as("each follow-up's effect was applied once across both processes")
        .isEqualTo(followUps);
    assertThat(
            count(
                "select count(distinct idempotency_key) from "
                    + RestartFixtureProcess.EFFECT_LOG_TABLE))
        .isEqualTo(followUps);
    for (String instance : List.of("first", "second")) {
      assertThat(
              count(
                  "select count(*) from "
                      + RestartFixtureProcess.EFFECT_LOG_TABLE
                      + " where instance = '"
                      + instance
                      + "'"))
          .as("the %s process took part in the queue", instance)
          .isPositive();
    }
    String publishType = AuditEnvelopeContract.PUBLISH_WORK_TYPE.value();
    assertThat(count("select count(*) from audit.publication_intent"))
        .isEqualTo(RestartFixtureProcess.SEEDED_MUTATIONS);
    assertThat(
            count(
                "select count(distinct payload ->> '"
                    + AuditEnvelopeContract.PAYLOAD_EVENT_ID
                    + "') from jobs.work_item where work_type = '"
                    + publishType
                    + "'"))
        .as("one publish item per publication intent")
        .isEqualTo(RestartFixtureProcess.SEEDED_MUTATIONS);
    assertThat(
            count(
                "select count(*) from "
                    + CLAIM_LOG_TABLE
                    + " where work_type = '"
                    + publishType
                    + "'"))
        .as("each publish item was claimed once, so each intent was published once")
        .isEqualTo(RestartFixtureProcess.SEEDED_MUTATIONS);
    assertThat(count("select count(*) from audit.event"))
        .as("one audit event per intent (the insert is idempotent: this would not show a repeat)")
        .isEqualTo(RestartFixtureProcess.SEEDED_MUTATIONS);
  }

  @Test
  void aBackendAskedToStopWhileItsReplacementRunsHandsItsItemOver() throws Exception {
    Process old =
        launch(
            "handover-old",
            LONG_LEASE,
            "old",
            RestartFixtureProcess.MODE_HANG_WHILE_LEASED,
            RestartFixtureProcess.SEED);
    Lease held = awaitTheOnlyLiveLease(old, "handover-old");
    assertThat(held.owner()).startsWith(OWNER_PREFIX + "old/");
    assertThat(held.attempts()).isEqualTo(1);

    Process replacement =
        launch(
            "handover-new",
            LONG_LEASE,
            "new",
            RestartFixtureProcess.MODE_NORMAL,
            RestartFixtureProcess.EFFECT_LOG);
    awaitEverythingElseSucceeded(old, replacement, "handover-old", "handover-new");
    await()
        .during(Duration.ofSeconds(2))
        .atMost(Duration.ofSeconds(30))
        .pollInterval(Duration.ofMillis(100))
        .until(() -> lease(held.id()).equals(held));
    assertThat(effects(held.id()))
        .as("the replacement kept polling for two seconds and left the live lease alone")
        .isEmpty();

    old.destroy();
    assertThat(old.waitFor(1, TimeUnit.MINUTES))
        .as("the old process stopped gracefully; log: %s", processes.tail("handover-old"))
        .isTrue();
    assertThat(processes.log("handover-old"))
        .as("the old process gave the item back itself, in a write fenced by its lease")
        .contains(givenBack(held.id()));
    await()
        .atMost(Duration.ofMinutes(1))
        .pollInterval(Duration.ofMillis(250))
        .ignoreExceptions()
        .untilAsserted(() -> {
          assertThat(replacement.isAlive())
              .as("replacement alive; log: %s", processes.tail("handover-new"))
              .isTrue();
          assertThat(count("select count(*) from jobs.work_item where status <> 'SUCCEEDED'"))
              .isZero();
        });

    Lease handedOver = lease(held.id());
    assertThat(handedOver.owner()).startsWith(OWNER_PREFIX + "new/");
    assertThat(handedOver.token()).as("a token exists only while RUNNING").isNull();
    assertThat(handedOver.attempts())
        .as("the attempt the old process gave back is not counted")
        .isEqualTo(1);
    assertThat(effects(held.id())).containsExactly(new Effect("new", 1));
    assertEveryOtherFollowUpWasAppliedOnce(held.id());
  }

  @Test
  void aBackendFinishingAfterItsLeaseExpiredCannotOverwriteTheReplacementsCompletion()
      throws Exception {
    Process old =
        launch(
            "fenced-old",
            LONG_LEASE,
            "old",
            RestartFixtureProcess.MODE_FINISH_AFTER_RECLAIMED,
            RestartFixtureProcess.EFFECT_LOG,
            RestartFixtureProcess.SEED);
    Lease held = awaitTheOnlyLiveLease(old, "fenced-old");
    assertThat(held.owner()).startsWith(OWNER_PREFIX + "old/");

    Process replacement =
        launch(
            "fenced-new",
            LONG_LEASE,
            "new",
            RestartFixtureProcess.MODE_NORMAL,
            RestartFixtureProcess.EFFECT_LOG);
    awaitEverythingElseSucceeded(old, replacement, "fenced-old", "fenced-new");
    assertThat(lease(held.id())).as("the live lease is left alone").isEqualTo(held);

    // The old process is still inside its handler; its lease runs out (here: is set to the past).
    execute(
        "update jobs.work_item set lease_expires_at = clock_timestamp() - interval '1 second'"
            + " where id = '"
            + held.id()
            + "'");
    await()
        .atMost(Duration.ofMinutes(1))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
          assertBothAlive(old, replacement, "fenced-old", "fenced-new");
          assertThat(processes.log("fenced-old"))
              .as("the old process applied its effect and its completion write was rejected")
              .contains(staleWriteRejected(held.id()));
        });

    Lease completed = lease(held.id());
    assertThat(completed.status()).isEqualTo("SUCCEEDED");
    assertThat(completed.owner())
        .as("the row is the replacement's completion")
        .startsWith(OWNER_PREFIX + "new/");
    assertThat(completed.token()).isNull();
    assertThat(completed.attempts()).as("reclaimed once the lease expired").isEqualTo(2);
    assertThat(effects(held.id()))
        .as("at least once: both applied the effect, under the item's one idempotency key")
        .containsExactly(new Effect("new", 2), new Effect("old", 1));
    assertThat(
            count(
                "select count(*) from jobs.work_item item where item.id = '"
                    + held.id()
                    + "' and item.finished_at < (select max(recorded_at) from "
                    + RestartFixtureProcess.EFFECT_LOG_TABLE
                    + " log where log.item_id = item.id and log.instance = 'old')"))
        .as("the completion time is the replacement's, from before the old process's late effect")
        .isEqualTo(1);
    assertThat(count("select count(*) from jobs.work_item where status <> 'SUCCEEDED'")).isZero();
    assertEveryOtherFollowUpWasAppliedOnce(held.id());
  }

  @Test
  void receiverDeduplicatesAfterRealProcessPausePastLeaseExpiry() throws Exception {
    interruptedAfterEffect(true);
  }

  @Test
  void receiverDeduplicatesAfterShutdownBetweenEffectAndCompletion() throws Exception {
    interruptedAfterEffect(false);
  }

  private void interruptedAfterEffect(boolean pause) throws Exception {
    Process old =
        launch(
            "receiver-old",
            Duration.ofSeconds(30),
            "old",
            RestartFixtureProcess.MODE_EFFECT_THEN_WAIT,
            RestartFixtureProcess.EFFECT_LOG,
            RestartFixtureProcess.DEDUPLICATE,
            RestartFixtureProcess.SEED);
    Lease held = awaitTheOnlyLiveLease(old, "receiver-old");
    await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
            assertThat(
                    count(
                        "select count(*) from "
                            + RestartFixtureProcess.RECEIVER_TABLE
                            + " where item_id = '"
                            + held.id()
                            + "'"))
                .isEqualTo(1));
    if (pause) signal(old, "STOP");
    Process replacement =
        launch(
            "receiver-new",
            Duration.ofSeconds(30),
            "new",
            RestartFixtureProcess.MODE_NORMAL,
            RestartFixtureProcess.EFFECT_LOG,
            RestartFixtureProcess.DEDUPLICATE);
    try {
      if (!pause) {
        old.destroy();
        assertThat(old.waitFor(1, TimeUnit.MINUTES)).isTrue();
      }
      await()
          .atMost(Duration.ofMinutes(2))
          .untilAsserted(() -> {
            assertThat(replacement.isAlive()).as(processes.tail("receiver-new")).isTrue();
            assertThat(count("select count(*) from jobs.work_item where status <> 'SUCCEEDED'"))
                .isZero();
          });
      Lease completed = lease(held.id());
      assertThat(completed.owner()).startsWith(OWNER_PREFIX + "new/");
      assertThat(completed.attempts()).isEqualTo(pause ? 2 : 1);
      assertThat(effects(held.id())).hasSize(2);
      assertThat(
              count(
                  "select count(*) from "
                      + RestartFixtureProcess.RECEIVER_TABLE
                      + " where item_id = '"
                      + held.id()
                      + "'"))
          .isEqualTo(1);
      if (pause) {
        signal(old, "CONT");
        await()
            .during(Duration.ofSeconds(3))
            .atMost(Duration.ofSeconds(10))
            .untilAsserted(() -> assertThat(lease(held.id())).isEqualTo(completed));
      }
      assertThat(count("select count(*) from " + RestartFixtureProcess.RECEIVER_TABLE))
          .isEqualTo(RestartFixtureProcess.SEEDED_FOLLOW_UPS);
    } finally {
      if (pause && old.isAlive()) signal(old, "CONT");
    }
  }

  @Test
  void shutdownDuringDatabaseStatementRollsBackOldTransaction() throws Exception {
    Process old =
        launch(
            "statement-old",
            Duration.ofSeconds(30),
            "old",
            RestartFixtureProcess.MODE_STATEMENT_WAIT,
            RestartFixtureProcess.EFFECT_LOG,
            RestartFixtureProcess.SEED);
    Lease held = awaitTheOnlyLiveLease(old, "statement-old");
    await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
            assertThat(
                    count(
                        "select count(*) from pg_stat_activity where state = 'active'"
                            + " and wait_event = 'PgSleep' and query like '%fixture-in-statement%'"))
                .isEqualTo(1));
    Process replacement =
        launch(
            "statement-new",
            LONG_LEASE,
            "new",
            RestartFixtureProcess.MODE_NORMAL,
            RestartFixtureProcess.EFFECT_LOG);
    awaitEverythingElseSucceeded(old, replacement, "statement-old", "statement-new");
    old.destroy();
    assertThat(old.waitFor(1, TimeUnit.MINUTES)).as(processes.tail("statement-old")).isTrue();
    await()
        .atMost(Duration.ofMinutes(1))
        .untilAsserted(() -> {
          assertThat(count("select count(*) from jobs.work_item where status <> 'SUCCEEDED'"))
              .isZero();
          assertThat(
                  count(
                      "select count(*) from pg_stat_activity where state = 'active'"
                          + " and wait_event = 'PgSleep' and query like '%fixture-in-statement%'"))
              .isZero();
        });
    assertThat(count("select count(*) from " + RestartFixtureProcess.TRANSACTION_TABLE))
        .as("the old handler inserted before its blocked statement; shutdown rolled it back")
        .isZero();
    assertThat(effects(held.id())).containsExactly(new Effect("new", 1));
    assertThat(lease(held.id()).owner()).startsWith(OWNER_PREFIX + "new/");
  }

  private static void signal(Process process, String signal) throws Exception {
    Process command =
        new ProcessBuilder("kill", "-" + signal, Long.toString(process.pid())).start();
    assertThat(command.waitFor(10, TimeUnit.SECONDS)).isTrue();
    assertThat(command.exitValue()).isZero();
  }

  @Test
  void migrationLockRetryBudgetFailsBoundedlyAndRestartCanRecover() throws Exception {
    try (Connection blocker = database.createConnection("");
        Statement statement = blocker.createStatement()) {
      blocker.setAutoCommit(false);
      statement.execute("create schema bootstrap");
      Process holder =
          launch("migration-holder", LONG_LEASE, "holder", RestartFixtureProcess.MODE_NORMAL);
      await()
          .atMost(STARTUP)
          .untilAsserted(() ->
              assertThat(
                      count(
                          "select count(*) from pg_locks where locktype = 'advisory' and granted"))
                  .isEqualTo(1));
      Process shortBudget =
          launch(
              "migration-short",
              LONG_LEASE,
              "short",
              "--spring.flyway.lock-retry-count=1",
              RestartFixtureProcess.MODE_NORMAL);
      assertThat(shortBudget.waitFor(30, TimeUnit.SECONDS))
          .as("bounded startup failure under a held migration lock")
          .isTrue();
      assertThat(shortBudget.exitValue()).isNotZero();
      assertThat(processes.log("migration-short"))
          .contains("lockRetryCount")
          .doesNotContain(RestartFixtureProcess.STARTED);
      Process restarted =
          launch(
              "migration-restart",
              LONG_LEASE,
              "restart",
              "--spring.flyway.lock-retry-count=10",
              RestartFixtureProcess.MODE_NORMAL);
      await()
          .atMost(STARTUP)
          .untilAsserted(() -> {
            assertThat(restarted.isAlive()).isTrue();
            assertThat(
                    count(
                        "select count(*) from pg_stat_activity where query like '%pg_try_advisory%'"
                            + " and pid <> pg_backend_pid() and pid not in (select pid from pg_locks"
                            + " where locktype = 'advisory' and granted)"))
                .isPositive();
          });
      blocker.rollback();
      await()
          .atMost(STARTUP)
          .untilAsserted(() -> {
            assertBothAlive(holder, restarted, "migration-holder", "migration-restart");
            assertThat(processes.log("migration-restart")).contains(RestartFixtureProcess.STARTED);
            assertThat(processes.log("migration-holder")).contains(RestartFixtureProcess.STARTED);
          });
    }
  }

  private Process launch(String name, Duration lease, String instance, String... fixtureArguments)
      throws IOException {
    List<String> arguments = new ArrayList<>(List.of(fixtureArguments));
    arguments.add("--owlmast.jobs.instance-id=" + instance);
    return processes.launch(database, name, lease, arguments.toArray(String[]::new));
  }

  /** The processor's log line (WorkProcessor) for a completion write under a lost lease. */
  private static String staleWriteRejected(UUID item) {
    return "Work item "
        + item
        + " (fixture.follow-up) lost its lease before completion; the write changed nothing";
  }

  /** The processor's log line (WorkProcessor) for the give-back of a cancelled dispatch. */
  private static String givenBack(UUID item) {
    return "Work item " + item + " (fixture.follow-up) given back uncounted: dispatch-cancelled";
  }

  private void assertBothAlive(Process one, Process other, String oneName, String otherName) {
    assertThat(one.isAlive()).as("%s alive; log: %s", oneName, processes.tail(oneName)).isTrue();
    assertThat(other.isAlive())
        .as("%s alive; log: %s", otherName, processes.tail(otherName))
        .isTrue();
  }

  /** Waits until the seeding process holds the one live lease of the database and returns it. */
  private Lease awaitTheOnlyLiveLease(Process holder, String name) {
    await()
        .atMost(STARTUP)
        .pollInterval(Duration.ofMillis(250))
        .ignoreExceptions()
        .untilAsserted(() -> {
          assertThat(holder.isAlive()).as("%s alive; log: %s", name, processes.tail(name)).isTrue();
          assertThat(processes.log(name)).contains(RestartFixtureProcess.READY);
          assertThat(count("select count(*) from jobs.work_item")).isEqualTo(SEEDED_WORK_ITEMS);
          assertThat(
                  count(
                      "select count(*) from jobs.work_item where status = 'RUNNING'"
                          + " and lease_expires_at > clock_timestamp()"))
              .isEqualTo(1);
        });
    try {
      return lease("status = 'RUNNING'");
    } catch (SQLException unreadable) {
      throw new AssertionError("the live lease could not be read", unreadable);
    }
  }

  /** Waits until the replacement finished every item but the one the old process holds. */
  private void awaitEverythingElseSucceeded(
      Process old, Process replacement, String oldName, String replacementName) {
    await()
        .atMost(STARTUP)
        .pollInterval(Duration.ofMillis(250))
        .ignoreExceptions()
        .untilAsserted(() -> {
          assertBothAlive(old, replacement, oldName, replacementName);
          assertThat(count("select count(*) from jobs.work_item where status = 'SUCCEEDED'"))
              .isEqualTo(SEEDED_WORK_ITEMS - 1);
          assertThat(
                  count("select count(*) from audit.publication_intent where published_at is null"))
              .isZero();
        });
  }

  private void assertEveryOtherFollowUpWasAppliedOnce(UUID held) throws SQLException {
    String others =
        " from " + RestartFixtureProcess.EFFECT_LOG_TABLE + " where item_id <> '" + held + "'";
    assertThat(count("select count(*)" + others))
        .as("every other follow-up's effect was applied once")
        .isEqualTo(RestartFixtureProcess.SEEDED_FOLLOW_UPS - 1);
    assertThat(count("select count(distinct idempotency_key)" + others))
        .isEqualTo(RestartFixtureProcess.SEEDED_FOLLOW_UPS - 1);
  }

  /** Every other session's state and last statement, for the messages of failed assertions. */
  private String sessions() {
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement();
        ResultSet rows =
            statement.executeQuery(
                "select pid, state, wait_event_type, left(query, 80) as query"
                    + " from pg_stat_activity"
                    + " where pid <> pg_backend_pid() and datname = current_database()"
                    + " order by pid")) {
      List<String> sessions = new ArrayList<>();
      while (rows.next()) {
        sessions.add(
            rows.getLong("pid")
                + " "
                + rows.getString("state")
                + " "
                + rows.getString("wait_event_type")
                + " "
                + rows.getString("query"));
      }
      return String.join(" | ", sessions);
    } catch (SQLException unreadable) {
      return "(sessions unavailable)";
    }
  }

  private void execute(String sql) throws SQLException {
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement()) {
      statement.execute(sql);
    }
  }

  private long count(String sql) throws SQLException {
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement()) {
      return scalar(statement, sql);
    }
  }

  private static long scalar(Statement statement, String sql) throws SQLException {
    try (ResultSet rows = statement.executeQuery(sql)) {
      rows.next();
      return rows.getLong(1);
    }
  }

  private Lease lease(UUID id) throws SQLException {
    return lease("id = '" + id + "'");
  }

  private Lease lease(String condition) throws SQLException {
    String sql =
        "select id, status, lease_owner, lease_token, attempt_count from jobs.work_item where "
            + condition;
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement();
        ResultSet rows = statement.executeQuery(sql)) {
      assertThat(rows.next()).as("exactly one row for: %s", sql).isTrue();
      Lease lease =
          new Lease(
              rows.getObject("id", UUID.class),
              rows.getString("status"),
              rows.getString("lease_owner"),
              rows.getObject("lease_token", UUID.class),
              rows.getInt("attempt_count"));
      assertThat(rows.next()).as("exactly one row for: %s", sql).isFalse();
      return lease;
    }
  }

  /** The effect log of one item, in the order the effects were recorded. */
  private List<Effect> effects(UUID item) throws SQLException {
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement();
        ResultSet rows =
            statement.executeQuery(
                "select instance, attempt from "
                    + RestartFixtureProcess.EFFECT_LOG_TABLE
                    + " where item_id = '"
                    + item
                    + "' order by recorded_at")) {
      List<Effect> effects = new ArrayList<>();
      while (rows.next()) {
        effects.add(new Effect(rows.getString("instance"), rows.getInt("attempt")));
      }
      return effects;
    }
  }
}
