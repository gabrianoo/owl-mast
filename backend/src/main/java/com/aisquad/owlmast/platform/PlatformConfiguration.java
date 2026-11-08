package com.aisquad.owlmast.platform;

import com.aisquad.owlmast.platform.blocking.BoundedBlocking;
import com.aisquad.owlmast.platform.blocking.BoundedBlockingProperties;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.reactive.TransactionalOperator;

/** Wires the platform primitives as singletons; features inject them through constructors. */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(BoundedBlockingProperties.class)
class PlatformConfiguration {

  @Bean(destroyMethod = "close")
  BoundedBlocking boundedBlocking(BoundedBlockingProperties properties) {
    return BoundedBlocking.create(properties);
  }

  /** Source of occurred/recorded times; tests may replace it with a fixed clock. */
  @Bean
  Clock clock() {
    return Clock.systemUTC();
  }

  @Bean
  ScopedTransactions scopedTransactions(
      TransactionalOperator transactionalOperator, DatabaseClient databaseClient) {
    return new ScopedTransactions(transactionalOperator, databaseClient);
  }
}
