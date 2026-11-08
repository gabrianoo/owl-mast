package com.aisquad.owlmast.jobs.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import com.aisquad.owlmast.jobs.api.WorkType;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;

class HandlerRegistryTest {

  @Test
  void resolvesHandlersByTypeAndRejectsDuplicates() {
    WorkHandler alpha = handler("alpha.one");
    WorkHandler beta = handler("beta.two");
    HandlerRegistry registry = new HandlerRegistry(List.of(alpha, beta));

    assertThat(registry.find(WorkType.of("alpha.one"))).contains(alpha);
    assertThat(registry.find(WorkType.of("missing"))).isEmpty();
    assertThat(registry.types())
        .containsExactlyInAnyOrder(WorkType.of("alpha.one"), WorkType.of("beta.two"));

    assertThatThrownBy(() -> new HandlerRegistry(List.of(alpha, handler("alpha.one"))))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("alpha.one");
  }

  private static WorkHandler handler(String type) {
    return new WorkHandler() {
      @Override
      public WorkRegistration registration() {
        return WorkRegistration.tenantInternal(WorkType.of(type));
      }

      @Override
      public Mono<EffectOutcome> handle(WorkItem item) {
        return Mono.just(EffectOutcome.applied(item.idempotencyKey()));
      }
    };
  }
}
