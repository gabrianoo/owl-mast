package com.aisquad.owlmast.jobs.adapter.config;

import com.aisquad.owlmast.jobs.api.DispatchAuthorization;
import com.aisquad.owlmast.jobs.api.FailedWorkQuery;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.application.FailedWorkQueryService;
import com.aisquad.owlmast.jobs.application.HandlerRegistry;
import com.aisquad.owlmast.jobs.application.TenantInternalOnlyDispatchAuthorization;
import com.aisquad.owlmast.jobs.application.WorkEnqueueService;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.util.UUID;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the jobs owner. Handlers are every {@link WorkHandler} bean in the context; the dispatch
 * authorization is the access module's bean when one exists (OM-02.04) and the fail-closed
 * tenant-internal default otherwise (AC7).
 */
@Slf4j
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(JobsProperties.class)
class JobsConfiguration {

  @Bean
  RetryPolicy retryPolicy(JobsProperties properties) {
    return properties.policy();
  }

  @Bean
  WorkEnqueue workEnqueue(
      ScopedTransactions transactions, WorkRepository repository, RetryPolicy policy) {
    return new WorkEnqueueService(transactions, repository, policy);
  }

  @Bean
  HandlerRegistry handlerRegistry(ObjectProvider<WorkHandler> handlers) {
    HandlerRegistry registry = new HandlerRegistry(handlers.orderedStream().toList());
    log.info("Durable work handlers registered: {}", registry.types());
    return registry;
  }

  @Bean
  WorkProcessor workProcessor(
      ScopedTransactions transactions,
      WorkRepository repository,
      HandlerRegistry registry,
      ObjectProvider<DispatchAuthorization> authorization,
      RetryPolicy policy) {
    DispatchAuthorization recheck =
        authorization.getIfAvailable(TenantInternalOnlyDispatchAuthorization::new);
    log.info("Dispatch authorization recheck: {}", recheck.getClass().getSimpleName());
    return new WorkProcessor(
        transactions,
        repository,
        registry,
        recheck,
        policy,
        "owl-mast-backend/" + UUID.randomUUID());
  }

  @Bean
  FailedWorkQuery failedWorkQuery(ScopedTransactions transactions, WorkRepository repository) {
    return new FailedWorkQueryService(transactions, repository);
  }
}
