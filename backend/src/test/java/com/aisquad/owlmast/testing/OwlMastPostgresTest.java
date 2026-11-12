package com.aisquad.owlmast.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * E01-R-02: the integration fixture provisions the application role the way an installation does.
 * The statements are written out in the fixture, so this compares them with the chart's
 * first-initialisation script; a change of the role's attributes or grants in the chart fails here
 * until the fixture follows.
 */
class OwlMastPostgresTest {

  private static final Path CHART_INIT =
      Path.of("..", "deploy", "helm", "owl-mast", "templates", "postgresql-init-configmap.yaml");

  /** The clauses of the chart's script that decide what the application role may do. */
  private static final List<String> ROLE_CONTRACT =
      List.of(
          "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION",
          "REVOKE ALL ON DATABASE",
          "GRANT CONNECT, TEMPORARY ON DATABASE",
          "CREATE EXTENSION IF NOT EXISTS vchord CASCADE;");

  @Test
  void theFixtureRoleCarriesTheAttributesAndGrantsOfTheChart() throws IOException {
    String chart = Files.readString(CHART_INIT);
    String fixture = OwlMastPostgres.initScript(true);

    assertThat(ROLE_CONTRACT)
        .allSatisfy(clause -> {
          assertThat(chart).as("chart init script").contains(clause);
          assertThat(fixture).as("fixture init script").contains(clause);
        });
    assertThat(chart)
        .as("the chart hands the database to the application role")
        .contains("CREATE DATABASE %I OWNER %I");
    assertThat(fixture)
        .contains("ALTER DATABASE owlmast OWNER TO " + OwlMastPostgres.APPLICATION_ROLE)
        .contains("CREATE ROLE " + OwlMastPostgres.APPLICATION_ROLE + " LOGIN PASSWORD");
  }

  @Test
  void thePlainImageGetsTheSameRoleWithoutTheExtension() {
    assertThat(OwlMastPostgres.initScript(false))
        .contains("NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION")
        .doesNotContain("vchord");
  }

  @Test
  void theApplicationRoleIsNotTheProvisioningSuperuser() {
    assertThat(OwlMastPostgres.APPLICATION_ROLE).isNotEqualTo(OwlMastPostgres.PROVISIONER);
  }
}
