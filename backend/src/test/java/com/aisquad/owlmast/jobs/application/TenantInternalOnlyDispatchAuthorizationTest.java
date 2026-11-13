package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

/**
 * AC7: the default recheck allows only tenant-internal system work whose type the jobs owner
 * granted, and denies everything else.
 */
class TenantInternalOnlyDispatchAuthorizationTest {

  private static final WorkType PUBLISH = WorkType.of("audit.publish");

  private final TenantInternalOnlyDispatchAuthorization authorization =
      new TenantInternalOnlyDispatchAuthorization(TenantInternalGrants.platformDefault());

  @Test
  void allowsGrantedTenantInternalSystemWork() {
    StepVerifier.create(
            authorization.recheck(item(PUBLISH), WorkRegistration.tenantInternal(PUBLISH)))
        .expectNext(DispatchDecision.ALLOW)
        .verifyComplete();
    StepVerifier.create(
            authorization.recheck(
                item(PUBLISH), WorkRegistration.tenantInternalRetriedWithoutLimit(PUBLISH)))
        .expectNext(DispatchDecision.ALLOW)
        .verifyComplete();
  }

  @Test
  void deniesHandlersThatRequireRealAuthorization() {
    WorkType type = WorkType.of("fixture.external");
    StepVerifier.create(
            authorization.recheck(item(type), WorkRegistration.requiresAuthorization(type)))
        .expectNext(DispatchDecision.DENY)
        .verifyComplete();
    // A granted type whose handler did not ask for the privilege is not given it.
    StepVerifier.create(
            authorization.recheck(item(PUBLISH), WorkRegistration.requiresAuthorization(PUBLISH)))
        .expectNext(DispatchDecision.DENY)
        .verifyComplete();
  }

  /** E01-R-03: saying tenant-internal is a request; without the grant the recheck denies. */
  @Test
  void deniesASelfDeclaredTenantInternalRegistrationOfAnUngrantedType() {
    WorkType selfGranted = WorkType.of("feature.self-granted");
    StepVerifier.create(
            authorization.recheck(item(selfGranted), WorkRegistration.tenantInternal(selfGranted)))
        .expectNext(DispatchDecision.DENY)
        .verifyComplete();
    StepVerifier.create(
            authorization.recheck(item(selfGranted), new WorkRegistration(selfGranted, true, true)))
        .expectNext(DispatchDecision.DENY)
        .verifyComplete();
  }

  /** A granted registration does not cover an item of another type. */
  @Test
  void deniesAnItemWhoseTypeIsNotTheRegistrationsType() {
    StepVerifier.create(
            authorization.recheck(
                item(WorkType.of("feature.other")), WorkRegistration.tenantInternal(PUBLISH)))
        .expectNext(DispatchDecision.DENY)
        .verifyComplete();
  }

  private static WorkItem item(WorkType type) {
    return new WorkItem(
        UUID.randomUUID(), new TenantId("aisquad"), type, 1, Map.of(), 1, 5, Optional.empty());
  }
}
