package com.aisquad.owlmast.compatibility.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.compatibility.api.ApiContractVersion;
import com.aisquad.owlmast.compatibility.api.CompatibilityDescriptor;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class CompatibilityServiceTest {

  @Test
  void describesServiceVersionAndContract() {
    StepVerifier.create(new CompatibilityService(new ApiContractVersion(1, 0), "0.1.0").describe())
        .assertNext(descriptor -> {
          assertThat(descriptor.service()).isEqualTo("owl-mast-backend");
          assertThat(descriptor.backendVersion()).isEqualTo("0.1.0");
          assertThat(descriptor.apiContract().label()).isEqualTo("1.0");
        })
        .verifyComplete();
  }

  @Test
  void rejectsNegativeOrBlankValues() {
    assertThatThrownBy(() -> new ApiContractVersion(-1, 0))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new CompatibilityDescriptor(" ", "v", new ApiContractVersion(1, 0)))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
