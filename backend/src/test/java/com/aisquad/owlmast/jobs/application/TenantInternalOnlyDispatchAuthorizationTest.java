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

/** AC7: the default recheck allows tenant-internal system work only and denies everything else. */
class TenantInternalOnlyDispatchAuthorizationTest {

  private final TenantInternalOnlyDispatchAuthorization authorization =
      new TenantInternalOnlyDispatchAuthorization();

  @Test
  void allowsTenantInternalSystemWork() {
    WorkType type = WorkType.of("audit.publish");
    StepVerifier.create(authorization.recheck(item(type), WorkRegistration.tenantInternal(type)))
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
  }

  private static WorkItem item(WorkType type) {
    return new WorkItem(
        UUID.randomUUID(), new TenantId("aisquad"), type, 1, Map.of(), 1, 5, Optional.empty());
  }
}
