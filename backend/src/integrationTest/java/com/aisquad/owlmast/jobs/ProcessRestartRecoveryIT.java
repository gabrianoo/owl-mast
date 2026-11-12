package com.aisquad.owlmast.jobs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

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
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * AC6 with genuinely separate application processes: a first JVM running the real application seeds
 * work and covered mutations, claims an item and halts itself ({@code Runtime.halt}, no shutdown
 * hooks, as a SIGKILL would end it) while holding the lease, so nothing ever releases it. A second
 * JVM against the same database finishes every item and publishes every intent through in-process
 * scheduling alone. The database is observed over JDBC from the test JVM, which runs no application
 * context of its own. The death happens from inside the handler, after the claim committed, so the
 * proof does not depend on an external kill landing before the handler deadline. This proves
 * process restart with Testcontainers; live Kubernetes pod replacement belongs to OM-18.02.
 *
 * <p>The second test covers the other way a process ends: a graceful shutdown (SIGTERM) while a
 * handler runs gives the item back at once and uncounted instead of leaving it leased.
 */
class ProcessRestartRecoveryIT {

  private static final Duration LEASE = Duration.ofSeconds(10);
  private static final String DEAD_OWNER_PREFIX = "owl-mast-backend/";
  private static final int SEEDED_WORK_ITEMS =
      RestartFixtureProcess.SEEDED_FOLLOW_UPS + RestartFixtureProcess.SEEDED_MUTATIONS;

  private static PostgreSQLContainer database;
  private static final List<Process> started = new ArrayList<>();
  private static Path logs;

  @BeforeAll
  static void startDatabase() throws IOException {
    database = OwlMastPostgres.vectorChord();
    database.start();
    logs = Files.createDirectories(Path.of("build", "restart-processes"));
  }

  @AfterAll
  static void stopEverything() {
    started.forEach(Process::destroyForcibly);
    if (database != null) {
      database.stop();
    }
  }

  @BeforeEach
  void emptyTheTables() throws SQLException {
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement()) {
      statement.execute(
          "do $$ begin"
              + " if to_regclass('jobs.work_item') is not null then"
              + " truncate jobs.work_item, audit.event, audit.publication_intent; end if;"
              + " if to_regclass('fixture_notes') is not null then truncate fixture_notes; end if;"
              + " end $$");
    }
  }

  /** One {@code jobs.work_item} row as seen over JDBC. */
  private record Lease(UUID id, String owner, UUID token, int attempts) {}

  @Test
  void aSeparateProcessFinishesTheWorkAndIntentsAKilledProcessLeftBehind() throws Exception {
    Process first =
        launch("first", RestartFixtureProcess.MODE_HALT_WHILE_LEASED, RestartFixtureProcess.SEED);
    assertThat(first.waitFor(2, TimeUnit.MINUTES))
        .as("the first process halted itself while holding a lease; log: %s", tail("first"))
        .isTrue();
    assertThat(first.exitValue()).isEqualTo(RestartFixtureProcess.HALT_EXIT_CODE);

    assertThat(count("select count(*) from jobs.work_item")).isEqualTo(SEEDED_WORK_ITEMS);
    assertThat(
            count(
                "select count(*) from jobs.work_item where status = 'RUNNING'"
                    + " and lease_expires_at > clock_timestamp()"))
        .as("the dead process left its lease live; nothing cleaned it up")
        .isEqualTo(1);
    Lease held = runningLease();
    assertThat(held.owner()).startsWith(DEAD_OWNER_PREFIX);
    assertThat(held.token()).isNotNull();
    assertThat(held.attempts()).isEqualTo(1);
    assertThat(count("select count(*) from jobs.work_item where status = 'SUCCEEDED'"))
        .as("the process died inside its first dispatch, so nothing else ran")
        .isZero();
    assertThat(count("select count(*) from audit.publication_intent where published_at is null"))
        .isEqualTo(RestartFixtureProcess.SEEDED_MUTATIONS);

    Process second = launch("second", "--fixture.mode=normal", "--fixture.seed=false");
    try {
      await()
          .atMost(Duration.ofMinutes(2))
          .pollInterval(Duration.ofMillis(250))
          .ignoreExceptions()
          .untilAsserted(() -> {
            assertThat(second.isAlive())
                .as("second process alive; log: %s", tail("second"))
                .isTrue();
            assertThat(count("select count(*) from jobs.work_item where status <> 'SUCCEEDED'"))
                .isZero();
            assertThat(
                    count(
                        "select count(*) from audit.publication_intent where published_at is null"))
                .isZero();
          });

      assertThat(count("select count(*) from jobs.work_item")).isEqualTo(SEEDED_WORK_ITEMS);
      assertThat(count("select count(*) from audit.event"))
          .isEqualTo(RestartFixtureProcess.SEEDED_MUTATIONS);
      Lease reclaimed = lease(held.id());
      assertThat(reclaimed.owner()).startsWith(DEAD_OWNER_PREFIX).isNotEqualTo(held.owner());
      assertThat(reclaimed.token()).as("a token exists only while RUNNING").isNull();
      assertThat(reclaimed.attempts()).as("reclaimed once the lease expired").isEqualTo(2);
      assertThat(
              count(
                  "select count(*) from jobs.work_item where attempt_count = 1 and id <> '"
                      + held.id()
                      + "'"))
          .as("every other item succeeded on its first attempt")
          .isEqualTo(SEEDED_WORK_ITEMS - 1);
      assertThat(count("select count(*) from jobs.work_item where effect_outcome = 'APPLIED'"))
          .isEqualTo(SEEDED_WORK_ITEMS);
    } finally {
      second.destroy();
      if (!second.waitFor(30, TimeUnit.SECONDS)) {
        second.destroyForcibly();
      }
    }
  }

  @Test
  void aGracefulShutdownGivesTheInFlightItemBackUncounted() throws Exception {
    // A lease far longer than the test, so only the shutdown can end it.
    Process hanging =
        launch(
            "hanging",
            Duration.ofMinutes(5),
            RestartFixtureProcess.MODE_HANG_WHILE_LEASED,
            RestartFixtureProcess.SEED);
    await()
        .atMost(Duration.ofMinutes(2))
        .pollInterval(Duration.ofMillis(250))
        .ignoreExceptions()
        .untilAsserted(() -> {
          assertThat(hanging.isAlive()).as("process alive; log: %s", tail("hanging")).isTrue();
          assertThat(count("select count(*) from jobs.work_item")).isEqualTo(SEEDED_WORK_ITEMS);
          assertThat(
                  count(
                      "select count(*) from jobs.work_item where status = 'RUNNING'"
                          + " and lease_expires_at > clock_timestamp()"))
              .isEqualTo(1);
        });
    Lease held = runningLease();
    assertThat(held.attempts()).isEqualTo(1);

    hanging.destroy();
    assertThat(hanging.waitFor(1, TimeUnit.MINUTES))
        .as("the process stopped gracefully; log: %s", tail("hanging"))
        .isTrue();

    assertThat(count("select count(*) from jobs.work_item where status = 'RUNNING'"))
        .as("no item is left leased until its five-minute lease expires; log: %s", tail("hanging"))
        .isZero();
    Lease givenBack = lease(held.id());
    assertThat(givenBack.token()).isNull();
    assertThat(givenBack.attempts()).as("the cancelled attempt is not counted").isZero();
    assertThat(
            count(
                "select count(*) from jobs.work_item where id = '"
                    + held.id()
                    + "' and status = 'PENDING' and failure_reason = 'dispatch-cancelled'"
                    + " and next_attempt_at <= clock_timestamp()"))
        .as("the item is due at once for the next instance")
        .isEqualTo(1);
    assertThat(count("select count(*) from jobs.work_item where status <> 'PENDING'"))
        .as("nothing else ran: the hanging handler held the serial dispatch")
        .isZero();
  }

  private static Process launch(String name, String... fixtureArguments) throws IOException {
    return launch(name, LEASE, fixtureArguments);
  }

  private static Process launch(String name, Duration lease, String... fixtureArguments)
      throws IOException {
    String java =
        ProcessHandle.current()
            .info()
            .command()
            .orElse(Path.of(System.getProperty("java.home"), "bin", "java").toString());
    List<String> command = new ArrayList<>();
    command.add(java);
    command.add("--enable-native-access=ALL-UNNAMED");
    command.add("-Xmx512m");
    command.add("-cp");
    command.add(System.getProperty("java.class.path"));
    command.add(RestartFixtureProcess.class.getName());
    command.add(
        "--spring.r2dbc.url=r2dbc:postgresql://"
            + database.getHost()
            + ":"
            + database.getFirstMappedPort()
            + "/"
            + database.getDatabaseName());
    command.add("--spring.r2dbc.username=" + database.getUsername());
    command.add("--spring.r2dbc.password=" + database.getPassword());
    command.add("--spring.flyway.url=" + database.getJdbcUrl());
    command.add("--spring.flyway.user=" + database.getUsername());
    command.add("--spring.flyway.password=" + database.getPassword());
    command.add("--server.port=0");
    command.add("--spring.main.banner-mode=off");
    command.add("--owlmast.jobs.scheduler.enabled=true");
    command.add("--owlmast.jobs.poll-interval=PT0.2S");
    command.add("--owlmast.jobs.lease-duration=" + lease);
    command.addAll(List.of(fixtureArguments));
    Process process =
        new ProcessBuilder(command)
            .redirectErrorStream(true)
            .redirectOutput(logs.resolve(name + ".log").toFile())
            .start();
    started.add(process);
    return process;
  }

  private static long count(String sql) throws SQLException {
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement();
        ResultSet rows = statement.executeQuery(sql)) {
      rows.next();
      return rows.getLong(1);
    }
  }

  private static Lease runningLease() throws SQLException {
    return lease(
        "select id, lease_owner, lease_token, attempt_count from jobs.work_item"
            + " where status = 'RUNNING'");
  }

  private static Lease lease(UUID id) throws SQLException {
    return lease(
        "select id, lease_owner, lease_token, attempt_count from jobs.work_item"
            + " where id = '"
            + id
            + "'");
  }

  private static Lease lease(String sql) throws SQLException {
    try (Connection connection = database.createConnection("");
        Statement statement = connection.createStatement();
        ResultSet rows = statement.executeQuery(sql)) {
      assertThat(rows.next()).as("exactly one row for: %s", sql).isTrue();
      Lease lease =
          new Lease(
              rows.getObject("id", UUID.class),
              rows.getString("lease_owner"),
              rows.getObject("lease_token", UUID.class),
              rows.getInt("attempt_count"));
      assertThat(rows.next()).as("exactly one row for: %s", sql).isFalse();
      return lease;
    }
  }

  private static String tail(String name) {
    try {
      List<String> lines = Files.readAllLines(logs.resolve(name + ".log"));
      return String.join("\n", lines.subList(Math.max(0, lines.size() - 15), lines.size()));
    } catch (IOException unreadable) {
      return "(log unavailable)";
    }
  }
}
