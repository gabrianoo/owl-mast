package com.aisquad.owlmast.compatibility.adapter.config;

import com.aisquad.owlmast.compatibility.api.CompatibilityQuery;
import com.aisquad.owlmast.compatibility.application.CompatibilityService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Wires the published contract and the build version (from build-info) into the query. */
@Configuration(proxyBeanMethods = false)
class CompatibilityConfiguration {

  static final String UNKNOWN_VERSION = "unknown";

  @Bean
  CompatibilityQuery compatibilityQuery(ObjectProvider<BuildProperties> buildProperties) {
    BuildProperties build = buildProperties.getIfAvailable();
    String version =
        build == null || build.getVersion() == null ? UNKNOWN_VERSION : build.getVersion();
    return new CompatibilityService(PublishedApiContract.load(), version);
  }
}
