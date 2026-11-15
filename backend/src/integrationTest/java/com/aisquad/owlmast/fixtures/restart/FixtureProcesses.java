package com.aisquad.owlmast.fixtures.restart;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * Starts {@link RestartFixtureProcess} JVMs against a database for the tests that need genuinely
 * separate application processes, and keeps one log file per process. The test JVM runs no
 * application context of its own.
 */
public final class FixtureProcesses {

  private final Path logs;
  private final List<Process> started = new ArrayList<>();

  public FixtureProcesses(Path logs) throws IOException {
    this.logs = Files.createDirectories(logs);
  }

  /**
   * Starts the real application with the fixture module in a JVM of its own, on the class path and
   * the Java launcher of the test JVM. The scheduler polls every 0.2 s; {@code lease} is the lease
   * duration of this process. Its output goes to {@code <logs>/<name>.log}.
   */
  public Process launch(
      PostgreSQLContainer database, String name, Duration lease, String... fixtureArguments)
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

  /** Everything the named process has written so far, or a placeholder when it is unreadable. */
  public String log(String name) {
    try {
      return Files.readString(logs.resolve(name + ".log"));
    } catch (IOException unreadable) {
      return "(log unavailable)";
    }
  }

  /** The last 15 lines of the named process's log, for assertion messages. */
  public String tail(String name) {
    List<String> lines = log(name).lines().toList();
    return String.join("\n", lines.subList(Math.max(0, lines.size() - 15), lines.size()));
  }

  /** Kills every process this instance started that is still alive. */
  public void stopAll() {
    started.forEach(Process::destroyForcibly);
    started.clear();
  }
}
