package com.aisquad.owlmast.fixtures.notes;

import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.jobs.application.TenantInternalGrants;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.util.HashSet;
import java.util.Set;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.r2dbc.core.DatabaseClient;

/** Registers the fixture module's handlers and service next to the production modules. */
@TestConfiguration(proxyBeanMethods = false)
public class NotesFixtureConfiguration {

  /**
   * The fixture module's follow-up handler is tenant-internal system work. Production code cannot
   * declare this bean (the feature-module rules keep {@code jobs.application} private to jobs); the
   * fixture adds its own type to the platform's grants so the audit publisher keeps working.
   */
  @Bean
  TenantInternalGrants tenantInternalGrants() {
    Set<WorkType> granted = new HashSet<>(TenantInternalGrants.platformDefault().types());
    granted.add(FollowUpHandler.TYPE);
    return new TenantInternalGrants(granted);
  }

  @Bean
  EffectStore effectStore() {
    return new EffectStore();
  }

  @Bean
  FollowUpHandler followUpHandler(EffectStore effects) {
    return new FollowUpHandler(effects);
  }

  @Bean
  ExternalHandler externalHandler() {
    return new ExternalHandler();
  }

  @Bean
  NotesFixture notesFixture(
      DatabaseClient databaseClient,
      ScopedTransactions transactions,
      WorkEnqueue enqueue,
      AuditedMutations audited) {
    return new NotesFixture(databaseClient, transactions, enqueue, audited);
  }

  @Bean
  DbProbe dbProbe(DatabaseClient databaseClient) {
    return new DbProbe(databaseClient);
  }
}
