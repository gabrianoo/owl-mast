package com.aisquad.owlmast.bootstrap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.aisquad.owlmast.OwlMastApplication;
import com.aisquad.owlmast.testing.OwlMastPostgres;
import org.junit.jupiter.api.Test;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.testcontainers.postgresql.PostgreSQLContainer;

/** AC4: a database without VectorChord must fail startup explicitly instead of degrading. */
class MissingExtensionIT {

  private static String causeChain(Throwable failure) {
    StringBuilder chain = new StringBuilder();
    for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
      chain.append(cause.getClass().getName()).append(": ").append(cause.getMessage()).append('\n');
    }
    return chain.toString();
  }

  private static String r2dbcUrl(PostgreSQLContainer container) {
    return "r2dbc:postgresql://%s:%d/%s"
        .formatted(
            container.getHost(),
            container.getMappedPort(PostgreSQLContainer.POSTGRESQL_PORT),
            container.getDatabaseName());
  }

  @Test
  void startupFailsNamingTheMissingVchordExtension() {
    try (PostgreSQLContainer plain = OwlMastPostgres.plainPostgres()) {
      plain.start();
      SpringApplicationBuilder application =
          new SpringApplicationBuilder(OwlMastApplication.class).web(WebApplicationType.NONE);
      // Command-line arguments outrank application.yaml defaults; builder.properties() would not.
      String[] args = {
        "--spring.flyway.url=" + plain.getJdbcUrl(),
        "--spring.flyway.user=" + plain.getUsername(),
        "--spring.flyway.password=" + plain.getPassword(),
        "--spring.r2dbc.url=" + r2dbcUrl(plain),
        "--spring.r2dbc.username=" + plain.getUsername(),
        "--spring.r2dbc.password=" + plain.getPassword(),
        // The identity contract is satisfied so the database failure is the one under test.
        "--owlmast.identity.issuer-uri=https://idp.example/realms/owl-mast",
      };

      Throwable failure = catchThrowable(() -> application.run(args));

      assertThat(failure).isNotNull();
      String causes = causeChain(failure);
      assertThat(causes)
          .contains("V001__bootstrap_infrastructure.sql")
          .contains("extension \"vchord\" is not available")
          .doesNotContain(plain.getPassword());
    }
  }
}
