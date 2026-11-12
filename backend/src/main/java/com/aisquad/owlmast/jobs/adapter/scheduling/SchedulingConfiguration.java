package com.aisquad.owlmast.jobs.adapter.scheduling;

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

  @Bean
  WorkScheduler workScheduler(WorkProcessor processor) {
    return new WorkScheduler(processor);
  }
}
