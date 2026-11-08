package com.aisquad.owlmast.compatibility.adapter.config;

import com.aisquad.owlmast.compatibility.api.ApiContractVersion;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Properties;

/**
 * Reads the published contract from {@code owlmast/api-contract.properties}, the single source that
 * the pre-rollout check ({@code scripts/check-api-compatibility.py}) also reads.
 */
public final class PublishedApiContract {

  public static final String RESOURCE = "owlmast/api-contract.properties";

  private PublishedApiContract() {}

  public static ApiContractVersion load() {
    try (InputStream stream =
        PublishedApiContract.class.getClassLoader().getResourceAsStream(RESOURCE)) {
      if (stream == null) {
        throw new IllegalStateException("Missing classpath resource " + RESOURCE);
      }
      Properties properties = new Properties();
      properties.load(stream);
      return parse(properties);
    } catch (IOException e) {
      throw new UncheckedIOException("Cannot read " + RESOURCE, e);
    }
  }

  static ApiContractVersion parse(Properties properties) {
    return new ApiContractVersion(
        requiredInt(properties, "apiContract.major"), requiredInt(properties, "apiContract.minor"));
  }

  private static int requiredInt(Properties properties, String key) {
    String value = properties.getProperty(key);
    if (value == null || value.isBlank()) {
      throw new IllegalStateException(RESOURCE + " is missing " + key);
    }
    try {
      return Integer.parseInt(value.trim());
    } catch (NumberFormatException e) {
      throw new IllegalStateException(RESOURCE + " has a non-integer " + key, e);
    }
  }
}
