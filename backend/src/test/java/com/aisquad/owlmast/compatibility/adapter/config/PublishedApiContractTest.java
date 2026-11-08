package com.aisquad.owlmast.compatibility.adapter.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Properties;
import org.junit.jupiter.api.Test;

class PublishedApiContractTest {

  @Test
  void loadsThePublishedContractFromTheClasspath() {
    assertThat(PublishedApiContract.load().label()).isEqualTo("1.0");
  }

  @Test
  void failsExplicitlyOnMissingOrMalformedKeys() {
    Properties missing = new Properties();
    missing.setProperty("apiContract.major", "1");
    assertThatThrownBy(() -> PublishedApiContract.parse(missing))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("apiContract.minor");

    Properties malformed = new Properties();
    malformed.setProperty("apiContract.major", "one");
    malformed.setProperty("apiContract.minor", "0");
    assertThatThrownBy(() -> PublishedApiContract.parse(malformed))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("apiContract.major");
  }
}
