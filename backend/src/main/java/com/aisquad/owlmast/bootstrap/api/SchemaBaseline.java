package com.aisquad.owlmast.bootstrap.api;

import java.time.Instant;
import java.util.Objects;

/** Extension versions recorded by the bootstrap migration when the schema baseline was applied. */
public record SchemaBaseline(String vchordVersion, String vectorVersion, Instant appliedAt) {

  public SchemaBaseline {
    Objects.requireNonNull(vchordVersion, "vchordVersion");
    Objects.requireNonNull(vectorVersion, "vectorVersion");
    Objects.requireNonNull(appliedAt, "appliedAt");
  }
}
