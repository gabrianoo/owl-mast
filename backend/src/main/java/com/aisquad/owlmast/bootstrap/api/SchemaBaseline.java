package com.aisquad.owlmast.bootstrap.api;

import java.time.Instant;
import java.util.Objects;

/**
 * Extension versions recorded by the bootstrap migration when the schema baseline was applied, and
 * the version of the PostgreSQL server that answered the read ({@code server_version_num}, for
 * example {@code 180003} for 18.3). The server version is not stored: a database can be moved to
 * another server after the baseline was recorded.
 */
public record SchemaBaseline(
    String vchordVersion, String vectorVersion, Instant appliedAt, int serverVersionNumber) {

  /**
   * Oldest supported PostgreSQL major version. The durable-work processor bounds every handler
   * transaction with {@code transaction_timeout}, which PostgreSQL 17 introduced; on an older
   * server every such statement fails, so every handler fails and unlimited-attempt work (audit
   * publication) retries forever.
   */
  public static final int MINIMUM_POSTGRESQL_MAJOR = 17;

  public SchemaBaseline {
    Objects.requireNonNull(vchordVersion, "vchordVersion");
    Objects.requireNonNull(vectorVersion, "vectorVersion");
    Objects.requireNonNull(appliedAt, "appliedAt");
    if (serverVersionNumber < 1) {
      throw new IllegalArgumentException("serverVersionNumber must be positive");
    }
  }

  /** Major version of the answering server ({@code server_version_num / 10000}). */
  public int postgresqlMajor() {
    return serverVersionNumber / 10_000;
  }

  public boolean serverIsSupported() {
    return postgresqlMajor() >= MINIMUM_POSTGRESQL_MAJOR;
  }
}
