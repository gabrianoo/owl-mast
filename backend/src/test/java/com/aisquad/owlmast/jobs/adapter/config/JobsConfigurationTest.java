package com.aisquad.owlmast.jobs.adapter.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;

/** The lease owner maps a lease back to the instance that held it and is safe to store and log. */
class JobsConfigurationTest {

  private static final UUID START = UUID.fromString("00000000-0000-0000-0000-00000000002a");

  @Test
  void theLeaseOwnerNamesTheInstanceAndTheStart() {
    assertThat(JobsConfiguration.leaseOwner("owl-mast-backend-7d9f8-x2k4q", START))
        .isEqualTo("owl-mast-backend/owl-mast-backend-7d9f8-x2k4q/" + START);
    assertThat(JobsConfiguration.leaseOwner("owl-mast-backend-7d9f8-x2k4q", UUID.randomUUID()))
        .as("two starts of one instance stay distinguishable")
        .isNotEqualTo(JobsConfiguration.leaseOwner("owl-mast-backend-7d9f8-x2k4q", START));
  }

  @Test
  void anInstanceIdIsReducedToABoundedSingleLineToken() {
    assertThat(JobsConfiguration.leaseOwner(" pod a\nforged line/x ", START))
        .isEqualTo("owl-mast-backend/pod_a_forged_line_x/" + START);
    assertThat(JobsConfiguration.leaseOwner("h".repeat(500), START))
        .isEqualTo(
            "owl-mast-backend/"
                + "h".repeat(JobsConfiguration.MAX_INSTANCE_ID_LENGTH)
                + "/"
                + START);
    for (String absent : new String[] {null, "", "   "}) {
      assertThat(JobsConfiguration.leaseOwner(absent, START))
          .isEqualTo("owl-mast-backend/unknown-host/" + START);
    }
  }
}
