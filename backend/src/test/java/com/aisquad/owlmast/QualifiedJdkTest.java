package com.aisquad.owlmast;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * The JVM that runs the tests must be the qualified JDK (OM-01.01-T1). The expected values come
 * from gradle.properties through the build; a missing property fails rather than skips.
 */
class QualifiedJdkTest {

  @Test
  void testsRunOnTheQualifiedJdkRuntime() {
    String expectedRuntime = System.getProperty("owlmast.qualified.jdk.runtime");
    String expectedVendor = System.getProperty("owlmast.qualified.jdk.vendor");

    assertThat(expectedRuntime).as("pin passed by the build").isNotBlank();
    assertThat(expectedVendor).as("vendor passed by the build").isNotBlank();
    assertThat(System.getProperty("java.runtime.version")).isEqualTo(expectedRuntime);
    assertThat(System.getProperty("java.vendor")).isEqualTo(expectedVendor);
    assertThat(Runtime.version().feature()).isEqualTo(27);
  }
}
