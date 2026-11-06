package com.aisquad.owlmast.platform.scope;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ScopesTest {

  private static final ScopeContext SCOPE = ScopeContext.of("aisquad", "person-1");

  @Test
  void boundScopeIsVisibleAcrossAsynchronousHops() {
    Mono<ScopeContext> read =
        Mono.just("request")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> Scopes.current())
            .publishOn(Schedulers.boundedElastic())
            .flatMap(first -> Scopes.current().map(second -> assertSame(first, second)))
            .contextWrite(Scopes.bind(SCOPE));

    StepVerifier.create(read).expectNext(SCOPE).verifyComplete();
  }

  @Test
  void absentScopeFailsClosed() {
    StepVerifier.create(Scopes.current())
        .expectErrorSatisfies(error ->
            assertThat(error)
                .isInstanceOf(MissingScopeException.class)
                .hasMessageContaining("Scopes.bind"))
        .verify();
  }

  @Test
  void identifiersRejectBlankValues() {
    assertThatThrownBy(() -> new TenantId(" ")).isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new PrincipalId("")).isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new ScopeContext(null, new PrincipalId("p")))
        .isInstanceOf(NullPointerException.class);
  }

  private static ScopeContext assertSame(ScopeContext first, ScopeContext second) {
    assertThat(second).isEqualTo(first);
    return second;
  }
}
