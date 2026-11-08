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
import org.junit.jupiter.api.Test;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * AC6 with genuinely separate application processes: a first JVM running the real application seeds
 * work and covered mutations, claims an item under a lease it never releases, and is killed with
 * SIGKILL while holding it. A second JVM against the same database finishes every item and
 * publishes every intent through in-process scheduling alone. The database is observed over JDBC
 * from the test JVM, which runs no application context of its own. This proves process restart with
 * Testcontainers; live Kubernetes pod replacement belongs to OM-18.02.
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

  /** One {@code jobs.work_item} row as seen over JDBC. */
  private record Lease(UUID id, String owner, UUID token, int attempts) {}

  @Test
  void aSeparateProcessFinishesTheWorkAndIntentsAKilledProcessLeftBehind() throws Exception {
    Process first = launch("first", RestartFixtureProcess.MODE_HANG, RestartFixtureProcess.SEED);
    Lease held;
    try {
      await()
          .atMost(Duration.ofMinutes(2))
          .pollInterval(Duration.ofMillis(250))
          .ignoreExceptions()
          .untilAsserted(() -> {
            assertThat(first.isAlive()).as("first process alive; log: %s", tail("first")).isTrue();
            assertThat(count("select count(*) from jobs.work_item")).isEqualTo(SEEDED_WORK_ITEMS);
            assertThat(
                    count(
                        "select count(*) from jobs.work_item where status = 'RUNNING'"
                            + " and lease_expires_at > clock_timestamp()"))
                .isEqualTo(1);
          });
      held = runningLease();
      assertThat(held.owner()).startsWith(DEAD_OWNER_PREFIX);
      assertThat(held.attempts()).isEqualTo(1);
      assertThat(count("select count(*) from jobs.work_item where status = 'SUCCEEDED'"))
          .as("the hanging handler blocks every other item behind it")
          .isZero();
      assertThat(count("select count(*) from audit.publication_intent where published_at is null"))
          .isEqualTo(RestartFixtureProcess.SEEDED_MUTATIONS);
    } finally {
      first.destroyForcibly();
      assertThat(first.waitFor(30, TimeUnit.SECONDS)).isTrue();
    }

    assertThat(first.isAlive()).isFalse();
    assertThat(runningLease())
        .as("the killed process left its lease live; nothing cleaned it up")
        .isEqualTo(held);
    assertThat(
            count(
                "select count(*) from jobs.work_item where status = 'RUNNING'"
                    + " and lease_expires_at > clock_timestamp()"))
        .isEqualTo(1);

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
      assertThat(reclaimed.token()).isNotEqualTo(held.token());
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

  private static Process launch(String name, String... fixtureArguments) throws IOException {
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
    command.add("--owlmast.jobs.lease-duration=" + LEASE);
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
