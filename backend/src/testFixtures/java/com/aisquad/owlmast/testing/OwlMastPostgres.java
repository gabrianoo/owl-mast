package com.aisquad.owlmast.testing;

import org.testcontainers.images.builder.Transferable;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * Factory for disposable PostgreSQL containers used by the integration suite.
 *
 * <p>The application never connects as a superuser here (E01-R-02). The image's own superuser is a
 * separate provisioning identity ({@link #PROVISIONER}); an init script, run by the image on first
 * start as that identity, creates the application role without any privileged attribute, hands it
 * the application database and installs VectorChord, the same sequence as the chart's {@code
 * 10-owl-mast-databases.sh}. Everything the container reports as its user ({@code getUsername()},
 * the Spring Boot service connection, {@code createConnection("")}) is the application role, so
 * Flyway migrations, the R2DBC runtime and the scheduler run under the restricted principal an
 * installation uses.
 */
public final class OwlMastPostgres {

  /** Application role and database: owner of its database, no superuser attribute. */
  public static final String APPLICATION_ROLE = "owlmast";

  /**
   * Provisioning superuser of the container; tests use it only to set up what an operator would.
   */
  public static final String PROVISIONER = "owlmast_provisioner";

  public static final String PROVISIONER_PASSWORD = "owlmast-integration-provisioner";

  private static final String DATABASE = "owlmast";
  private static final String APPLICATION_PASSWORD = "owlmast-integration-test";
  private static final String INIT_SCRIPT_PATH =
      "/docker-entrypoint-initdb.d/10-owl-mast-owner.sql";

  private OwlMastPostgres() {}

  /** The qualified VectorChord image; the caller (or Spring) owns start/stop. */
  public static PostgreSQLContainer vectorChord() {
    return container(OwlMastImages.VECTORCHORD_POSTGRES);
  }

  /** A plain PostgreSQL image for negative extension tests only. */
  public static PostgreSQLContainer plainPostgres() {
    return container(OwlMastImages.PLAIN_POSTGRES);
  }

  /**
   * The image's default command preloads VectorChord ({@code postgres -c
   * shared_preload_libraries=vchord,vector}); Testcontainers replaces the command, so the preload
   * must be restated or {@code CREATE EXTENSION vchord} fails with "must be loaded via
   * shared_preload_libraries".
   */
  static final String[] VECTORCHORD_COMMAND = {
    "postgres", "-c", "shared_preload_libraries=vchord,vector", "-c", "fsync=off"
  };

  /**
   * Run by the image entrypoint as the provisioning superuser, connected to the application
   * database it created. The role attributes and grants are the chart's.
   */
  static String initScript(boolean installVectorChord) {
    return """
    CREATE ROLE %1$s LOGIN PASSWORD '%2$s'
        NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
    ALTER DATABASE %3$s OWNER TO %1$s;
    REVOKE ALL ON DATABASE %3$s FROM PUBLIC;
    GRANT CONNECT, TEMPORARY ON DATABASE %3$s TO %1$s;
    """
            .formatted(APPLICATION_ROLE, APPLICATION_PASSWORD, DATABASE)
        // VectorChord is installed by the provisioning identity, so the application role never
        // needs superuser; the bootstrap migration's CREATE EXTENSION IF NOT EXISTS is then a
        // no-op.
        + (installVectorChord ? "CREATE EXTENSION IF NOT EXISTS vchord CASCADE;\n" : "");
  }

  private static PostgreSQLContainer container(DockerImageName image) {
    ContainerRuntime.requireAvailable();
    boolean vectorChord = image.equals(OwlMastImages.VECTORCHORD_POSTGRES);
    PostgreSQLContainer container = new RestrictedOwnerPostgres(image);
    if (vectorChord) {
      container.setCommand(VECTORCHORD_COMMAND);
    }
    container.withCopyToContainer(Transferable.of(initScript(vectorChord)), INIT_SCRIPT_PATH);
    return container
        .withDatabaseName(DATABASE)
        .withUsername(APPLICATION_ROLE)
        .withPassword(APPLICATION_PASSWORD);
  }

  /**
   * Reports the application role as its user while the image initialises under the provisioning
   * superuser: Testcontainers derives {@code POSTGRES_USER} from the reported user, so the
   * environment is corrected after it was derived.
   */
  private static final class RestrictedOwnerPostgres extends PostgreSQLContainer {

    RestrictedOwnerPostgres(DockerImageName image) {
      super(image);
    }

    @Override
    protected void configure() {
      super.configure();
      addEnv("POSTGRES_USER", PROVISIONER);
      addEnv("POSTGRES_PASSWORD", PROVISIONER_PASSWORD);
    }
  }
}
