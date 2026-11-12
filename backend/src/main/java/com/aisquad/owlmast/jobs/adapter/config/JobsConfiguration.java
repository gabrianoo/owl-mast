package com.aisquad.owlmast.jobs.adapter.config;

import com.aisquad.owlmast.jobs.api.DispatchAuthorization;
import com.aisquad.owlmast.jobs.api.FailedWorkQuery;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.application.FailedWorkQueryService;
import com.aisquad.owlmast.jobs.application.HandlerRegistry;
import com.aisquad.owlmast.jobs.application.TenantInternalGrants;
import com.aisquad.owlmast.jobs.application.TenantInternalOnlyDispatchAuthorization;
import com.aisquad.owlmast.jobs.application.WorkEnqueueService;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.UUID;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the jobs owner. Handlers are every {@link WorkHandler} bean in the context; a handler may
 * register as tenant-internal system work only for a type in {@link TenantInternalGrants}; the
 * dispatch authorization is the access module's bean when one exists (OM-02.04) and the fail-closed
 * tenant-internal default otherwise (AC7). The lease owner written to {@code lease_owner} names
 * this instance ({@code owlmast.jobs.instance-id}, by default {@code HOSTNAME} or the local host
 * name, which is the pod name on Kubernetes) plus a random part per start, and is logged once at
 * startup.
 */
@Slf4j
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(JobsProperties.class)
class JobsConfiguration {

  static final String LEASE_OWNER_PREFIX = "owl-mast-backend/";
  static final int MAX_INSTANCE_ID_LENGTH = 128;

  @Bean
  RetryPolicy retryPolicy(JobsProperties properties) {
    return properties.policy();
  }

  @Bean
  WorkEnqueue workEnqueue(
      ScopedTransactions transactions,
      WorkRepository repository,
      RetryPolicy policy,
      ObjectProvider<HandlerRegistry> registry) {
    // Resolved on first use: a handler may itself enqueue follow-up work.
    return new WorkEnqueueService(transactions, repository, policy, registry::getObject);
  }

  @Bean
  HandlerRegistry handlerRegistry(
      ObjectProvider<WorkHandler> handlers, ObjectProvider<TenantInternalGrants> grants) {
    TenantInternalGrants granted = granted(grants);
    HandlerRegistry registry = new HandlerRegistry(handlers.orderedStream().toList(), granted);
    log.info(
        "Durable work handlers registered: {}; tenant-internal system work granted to: {}",
        registry.types(),
        granted.types());
    return registry;
  }

  @Bean
  WorkProcessor workProcessor(
      ScopedTransactions transactions,
      WorkRepository repository,
      HandlerRegistry registry,
      ObjectProvider<DispatchAuthorization> authorization,
      ObjectProvider<TenantInternalGrants> grants,
      RetryPolicy policy,
      @Value("${owlmast.jobs.instance-id:${HOSTNAME:}}") String instanceId) {
    DispatchAuthorization recheck =
        authorization.getIfAvailable(
            () -> new TenantInternalOnlyDispatchAuthorization(granted(grants)));
    log.info("Dispatch authorization recheck: {}", recheck.getClass().getSimpleName());
    String leaseOwner =
        leaseOwner(instanceId.isBlank() ? localHostName() : instanceId, UUID.randomUUID());
    log.info("Durable work lease owner of this instance: {}", leaseOwner);
    return new WorkProcessor(transactions, repository, registry, recheck, policy, leaseOwner);
  }

  /**
   * The grants the registry and the default recheck share. There is no such bean in production: the
   * feature-module rules keep {@link TenantInternalGrants} private to jobs, so only a test fixture
   * can supply another instance.
   */
  private static TenantInternalGrants granted(ObjectProvider<TenantInternalGrants> grants) {
    return grants.getIfAvailable(TenantInternalGrants::platformDefault);
  }

  /** The host name when neither the setting nor {@code HOSTNAME} names the instance. */
  private static String localHostName() {
    try {
      return InetAddress.getLocalHost().getHostName();
    } catch (UnknownHostException unresolved) {
      return "";
    }
  }

  /**
   * {@code owl-mast-backend/<instance>/<random>}: the instance part maps a lease back to the pod or
   * host that held it, the random part tells two starts of the same instance apart. The instance id
   * is reduced to a bounded, single-line token so it is safe in the column and in log lines.
   */
  static String leaseOwner(String instanceId, UUID startId) {
    String token = instanceId == null ? "" : instanceId.strip().replaceAll("[^A-Za-z0-9._-]", "_");
    if (token.length() > MAX_INSTANCE_ID_LENGTH) {
      token = token.substring(0, MAX_INSTANCE_ID_LENGTH);
    }
    return LEASE_OWNER_PREFIX + (token.isEmpty() ? "unknown-host" : token) + "/" + startId;
  }

  @Bean
  FailedWorkQuery failedWorkQuery(ScopedTransactions transactions, WorkRepository repository) {
    return new FailedWorkQueryService(transactions, repository);
  }
}
