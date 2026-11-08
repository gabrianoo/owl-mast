package com.aisquad.owlmast.fixtures.notes;

import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.r2dbc.core.DatabaseClient;

/** Registers the fixture module's handlers and service next to the production modules. */
@TestConfiguration(proxyBeanMethods = false)
public class NotesFixtureConfiguration {

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
