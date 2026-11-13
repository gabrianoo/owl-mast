package com.aisquad.owlmast.jobs.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import com.aisquad.owlmast.jobs.api.WorkType;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;

class HandlerRegistryTest {

  private static final WorkType ALPHA = WorkType.of("alpha.one");
  private static final WorkType BETA = WorkType.of("beta.two");
  private static final TenantInternalGrants GRANTS = new TenantInternalGrants(Set.of(ALPHA, BETA));

  @Test
  void resolvesHandlersByTypeAndRejectsDuplicates() {
    WorkHandler alpha = handler(WorkRegistration.tenantInternal(ALPHA));
    WorkHandler beta = handler(WorkRegistration.tenantInternal(BETA));
    HandlerRegistry registry = new HandlerRegistry(List.of(alpha, beta), GRANTS);

    assertThat(registry.find(ALPHA)).contains(alpha);
    assertThat(registry.find(WorkType.of("missing"))).isEmpty();
    assertThat(registry.registration(WorkType.of("missing"))).isEmpty();
    assertThat(registry.types()).containsExactlyInAnyOrder(ALPHA, BETA);

    List<WorkHandler> duplicate = List.of(alpha, handler(WorkRegistration.tenantInternal(ALPHA)));
    assertThatThrownBy(() -> new HandlerRegistry(duplicate, GRANTS))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("alpha.one");
  }

  /**
   * E01-R-03 (retro R1, PR #110 thread on AC7): a handler cannot make itself tenant-internal system
   * work. Declaring it for a type the jobs owner has not granted stops the application from
   * starting, in both forms of the declaration.
   */
  @Test
  void aHandlerCannotGrantItselfTheTenantInternalPrivilege() {
    WorkType selfGranted = WorkType.of("feature.self-granted");

    for (WorkRegistration declared :
        List.of(
            WorkRegistration.tenantInternal(selfGranted),
            WorkRegistration.tenantInternalRetriedWithoutLimit(selfGranted),
            new WorkRegistration(selfGranted, true),
            new WorkRegistration(selfGranted, true, true))) {
      List<WorkHandler> handlers = List.of(handler(declared));
      assertThatThrownBy(() -> new HandlerRegistry(handlers, GRANTS))
          .isInstanceOf(IllegalStateException.class)
          .hasMessageContaining("feature.self-granted")
          .hasMessageContaining("tenant-internal system work")
          .hasMessageContaining("TenantInternalGrants");
    }
  }

  @Test
  void workThatAsksForNoPrivilegeNeedsNoGrant() {
    WorkType ordinary = WorkType.of("feature.ordinary");
    WorkHandler handler = handler(WorkRegistration.requiresAuthorization(ordinary));

    HandlerRegistry registry =
        new HandlerRegistry(List.of(handler), TenantInternalGrants.platformDefault());

    assertThat(registry.registration(ordinary))
        .hasValueSatisfying(
            registration -> assertThat(registration.tenantInternalSystemWork()).isFalse());
  }

  /** The registration read at startup is the one used later, whatever the handler then answers. */
  @Test
  void aRegistrationChangedAfterStartupIsNotSeen() {
    WorkType ordinary = WorkType.of("feature.ordinary");
    AtomicReference<WorkRegistration> answer =
        new AtomicReference<>(WorkRegistration.requiresAuthorization(ordinary));
    WorkHandler shifting =
        new WorkHandler() {
          @Override
          public WorkRegistration registration() {
            return answer.get();
          }

          @Override
          public Mono<EffectOutcome> handle(WorkItem item) {
            return Mono.just(EffectOutcome.applied(item.idempotencyKey()));
          }
        };
    HandlerRegistry registry = new HandlerRegistry(List.of(shifting), GRANTS);

    answer.set(WorkRegistration.tenantInternalRetriedWithoutLimit(ordinary));

    assertThat(registry.registration(ordinary))
        .hasValueSatisfying(registration -> {
          assertThat(registration.tenantInternalSystemWork()).isFalse();
          assertThat(registration.unlimitedAttempts()).isFalse();
        });
  }

  @Test
  void thePlatformGrantsAreClosedAndImmutable() {
    TenantInternalGrants grants = TenantInternalGrants.platformDefault();

    assertThat(grants.types()).containsExactly(WorkType.of("audit.publish"));
    assertThat(grants.contains(WorkType.of("audit.publish"))).isTrue();
    assertThat(grants.contains(ALPHA)).isFalse();
    assertThatThrownBy(() -> grants.types().add(ALPHA))
        .isInstanceOf(UnsupportedOperationException.class);
  }

  private static WorkHandler handler(WorkRegistration registration) {
    return new WorkHandler() {
      @Override
      public WorkRegistration registration() {
        return registration;
      }

      @Override
      public Mono<EffectOutcome> handle(WorkItem item) {
        return Mono.just(EffectOutcome.applied(item.idempotencyKey()));
      }
    };
  }
}
