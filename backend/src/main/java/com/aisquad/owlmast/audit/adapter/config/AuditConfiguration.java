package com.aisquad.owlmast.audit.adapter.config;

import com.aisquad.owlmast.audit.api.AuditHistoryQuery;
import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.audit.application.AuditHistoryQueryService;
import com.aisquad.owlmast.audit.application.AuditPublishHandler;
import com.aisquad.owlmast.audit.application.AuditedMutationService;
import com.aisquad.owlmast.audit.port.AuditStore;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.time.Clock;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.support.DefaultTransactionDefinition;

/**
 * Wires the audit owner. The separate outcome path uses a {@code PROPAGATION_REQUIRES_NEW} scoped
 * transaction so a failed or denied record commits even when the caller holds a transaction that is
 * rolling back (AC3). That transaction takes a second connection while the failing one still holds
 * its own; connections are unpooled, so this fails fast at the server limit instead of waiting. A
 * future pool must leave that headroom (see the contract document, durability path step 5).
 */
@Configuration(proxyBeanMethods = false)
class AuditConfiguration {

  @Bean
  AuditedMutations auditedMutations(
      ScopedTransactions transactions,
      ReactiveTransactionManager transactionManager,
      DatabaseClient databaseClient,
      AuditStore store,
      WorkEnqueue enqueue,
      Clock clock,
      @Value("${owlmast.audit.outcome-write-deadline:PT5S}") Duration outcomeWriteDeadline) {
    DefaultTransactionDefinition requiresNew = new DefaultTransactionDefinition();
    requiresNew.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    ScopedTransactions separate =
        new ScopedTransactions(
            TransactionalOperator.create(transactionManager, requiresNew), databaseClient);
    return new AuditedMutationService(
        transactions, separate, store, enqueue, clock, outcomeWriteDeadline);
  }

  @Bean
  AuditPublishHandler auditPublishHandler(AuditStore store) {
    return new AuditPublishHandler(store);
  }

  @Bean
  AuditHistoryQuery auditHistoryQuery(ScopedTransactions transactions, AuditStore store) {
    return new AuditHistoryQueryService(transactions, store);
  }
}
