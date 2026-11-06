package com.aisquad.owlmast.bootstrap.application;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SchemaBaselineServiceTest {

  @Test
  void exposesTheRepositoryAnswerThroughThePublicApi() {
    SchemaBaseline baseline = new SchemaBaseline("1.1.1", "0.8.2", Instant.EPOCH);

    StepVerifier.create(new SchemaBaselineService(() -> Mono.just(baseline)).current())
        .expectNext(baseline)
        .verifyComplete();
    StepVerifier.create(new SchemaBaselineService(Mono::empty).current()).verifyComplete();
  }
}
