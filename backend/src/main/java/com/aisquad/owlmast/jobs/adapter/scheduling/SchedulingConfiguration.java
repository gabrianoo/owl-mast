package com.aisquad.owlmast.jobs.adapter.scheduling;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import com.aisquad.owlmast.bootstrap.api.SchemaBaselineQuery;
import com.aisquad.owlmast.jobs.application.WorkProcessor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Enables in-process scheduling and registers the wake-up. {@code owlmast.jobs.scheduler.enabled}
 * exists for tests that drive the processor explicitly; production leaves it on.
 */
@Configuration(proxyBeanMethods = false)
@EnableScheduling
@ConditionalOnProperty(
    name = "owlmast.jobs.scheduler.enabled",
    havingValue = "true",
    matchIfMissing = true)
class SchedulingConfiguration {

  /**
   * Every wake-up asks the schema baseline again and claims work only while it reports a supported
   * server (PostgreSQL 17 or newer); a missing, unreadable or unanswered (longer than {@link
   * WorkScheduler#PRECONDITION_TIMEOUT}) baseline counts as not supported for that wake-up.
   */
  @Bean
  WorkScheduler workScheduler(WorkProcessor processor, SchemaBaselineQuery schemaBaseline) {
    return new WorkScheduler(
        processor, () -> schemaBaseline.current().map(SchemaBaseline::serverIsSupported));
  }
}
