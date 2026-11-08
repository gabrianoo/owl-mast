package com.aisquad.owlmast.compatibility.application;

import com.aisquad.owlmast.compatibility.api.ApiContractVersion;
import com.aisquad.owlmast.compatibility.api.CompatibilityDescriptor;
import com.aisquad.owlmast.compatibility.api.CompatibilityQuery;
import reactor.core.publisher.Mono;

/** Assembles the descriptor from the published contract and the build version. */
public final class CompatibilityService implements CompatibilityQuery {

  static final String SERVICE = "owl-mast-backend";

  private final CompatibilityDescriptor descriptor;

  public CompatibilityService(ApiContractVersion apiContract, String backendVersion) {
    this.descriptor = new CompatibilityDescriptor(SERVICE, backendVersion, apiContract);
  }

  @Override
  public Mono<CompatibilityDescriptor> describe() {
    return Mono.just(descriptor);
  }
}
