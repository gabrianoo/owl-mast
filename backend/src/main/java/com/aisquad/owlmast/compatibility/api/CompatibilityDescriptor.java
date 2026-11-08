package com.aisquad.owlmast.compatibility.api;

import java.util.Objects;

/** What the backend publishes about itself: service name, build version and API contract. */
public record CompatibilityDescriptor(
    String service, String backendVersion, ApiContractVersion apiContract) {

  public CompatibilityDescriptor {
    Objects.requireNonNull(service, "service");
    Objects.requireNonNull(backendVersion, "backendVersion");
    Objects.requireNonNull(apiContract, "apiContract");
    if (service.isBlank() || backendVersion.isBlank()) {
      throw new IllegalArgumentException("service and backendVersion must not be blank");
    }
  }
}
