package com.aisquad.owlmast.buildlogic;

import java.util.Map;
import org.gradle.api.GradleException;
import org.gradle.jvm.toolchain.JavaInstallationMetadata;

/**
 * Enforces the qualified JDK build (OM-01.01-T1) on the JVM a task actually resolved. Toolchain
 * criteria only constrain the major version and vendor; this guard compares the exact runtime
 * version recorded in gradle.properties (docs/toolchain-qualification.md).
 */
public final class QualifiedJdk {

  /** Distribution name reported by toolchain metadata for the vendor reported by the JVM. */
  private static final Map<String, String> DISTRIBUTION_NAMES =
      Map.of("Eclipse Adoptium", "Eclipse Temurin");

  private QualifiedJdk() {}

  public static void require(
      JavaInstallationMetadata metadata,
      String role,
      String qualifiedRuntime,
      String qualifiedVendor) {
    String actualRuntime = metadata.getJavaRuntimeVersion();
    String actualVendor = metadata.getVendor();
    boolean vendorMatches =
        actualVendor.equals(qualifiedVendor)
            || actualVendor.equals(DISTRIBUTION_NAMES.get(qualifiedVendor));
    if (!actualRuntime.equals(qualifiedRuntime) || !vendorMatches) {
      throw new GradleException(
          role
              + " JVM '"
              + actualVendor
              + " "
              + actualRuntime
              + "' at "
              + metadata.getInstallationPath().getAsFile()
              + " is not the qualified JDK '"
              + qualifiedVendor
              + " "
              + qualifiedRuntime
              + "' (docs/toolchain-qualification.md).");
    }
  }
}
