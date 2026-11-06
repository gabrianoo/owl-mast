package com.aisquad.owlmast.testing;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;

/**
 * Registers the VectorChord container as a Spring-managed service connection: Boot derives the
 * R2DBC, JDBC and Flyway connection details and stops the container with the context.
 */
@TestConfiguration(proxyBeanMethods = false)
public class ContainersConfiguration {

  @Bean
  @ServiceConnection
  PostgreSQLContainer owlMastDatabase() {
    return OwlMastPostgres.vectorChord();
  }
}
