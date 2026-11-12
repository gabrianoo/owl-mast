package com.aisquad.owlmast.jobs.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.platform.scope.TenantId;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** AC9: the published work-item types validate their bounds and derive a stable idempotency key. */
class WorkContractTypesTest {

  private static final WorkType TYPE = WorkType.of("fixture.follow-up");

  @Test
  void idempotencyKeyIsDerivedFromTheItemAndStableAcrossAttempts() {
    UUID id = UUID.randomUUID();
    WorkItem first = item(id, 1);
    WorkItem reclaimed = item(id, 2);

    assertThat(first.idempotencyKey()).isEqualTo("owlmast-work:" + id);
    assertThat(reclaimed.idempotencyKey()).isEqualTo(first.idempotencyKey());
    assertThat(first.lastAttempt()).isFalse();
    assertThat(item(id, 3).lastAttempt()).isTrue();
  }

  @Test
  void payloadIsCopiedAndBounded() {
    Map<String, String> mutable = new HashMap<>(Map.of("noteId", "n-1"));
    EnqueueRequest request = EnqueueRequest.of(TYPE, mutable);
    mutable.put("later", "x");

    assertThat(request.payload()).containsOnlyKeys("noteId");
    assertThatThrownBy(() -> request.payload().put("k", "v"))
        .isInstanceOf(UnsupportedOperationException.class);

    Map<String, String> tooMany = new HashMap<>();
    for (int i = 0; i <= WorkItemContract.MAX_PAYLOAD_ENTRIES; i++) {
      tooMany.put("k" + i, "v");
    }
    assertThatThrownBy(() -> EnqueueRequest.of(TYPE, tooMany))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("entries");
    assertThatThrownBy(() ->
            EnqueueRequest.of(
                TYPE, Map.of("k", "v".repeat(WorkItemContract.MAX_PAYLOAD_VALUE_LENGTH + 1))))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> EnqueueRequest.of(TYPE, Map.of("k", "v"), " "))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("correlation");
  }

  @Test
  void correlationIdBoundaryMatchesTheAuditEnvelope() {
    assertThat(WorkItemContract.MAX_CORRELATION_ID_LENGTH).isEqualTo(256);
    String atLimit = "c".repeat(WorkItemContract.MAX_CORRELATION_ID_LENGTH);
    assertThat(EnqueueRequest.of(TYPE, Map.of(), atLimit).correlationId()).contains(atLimit);
    assertThatThrownBy(() -> EnqueueRequest.of(TYPE, Map.of(), atLimit + "x"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("correlation");
  }

  @Test
  void workTypesAreLowerCaseDottedSegments() {
    assertThat(WorkType.of("audit.publish").value()).isEqualTo("audit.publish");
    assertThatThrownBy(() -> WorkType.of("Audit.Publish"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> WorkType.of("audit..publish"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> WorkType.of("")).isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void effectOutcomesCarryIdentifierReferencesOnly() {
    assertThat(EffectOutcome.applied("owlmast-work:1")).isInstanceOf(EffectOutcome.Applied.class);
    assertThat(EffectOutcome.uncertain("remote:42").reference()).isEqualTo("remote:42");
    assertThatThrownBy(() -> EffectOutcome.applied(" "))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() ->
            EffectOutcome.applied("x".repeat(WorkItemContract.MAX_EFFECT_REFERENCE_LENGTH + 1)))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void terminalStatusesAreTheFourNonLiveOnes() {
    assertThat(WorkStatus.PENDING.terminal()).isFalse();
    assertThat(WorkStatus.RUNNING.terminal()).isFalse();
    assertThat(WorkStatus.SUCCEEDED.terminal()).isTrue();
    assertThat(WorkStatus.FAILED.terminal()).isTrue();
    assertThat(WorkStatus.DENIED.terminal()).isTrue();
    assertThat(WorkStatus.OUTCOME_UNCERTAIN.terminal()).isTrue();
  }

  @Test
  void failedWorkItemsRefuseLiveOrSucceededStatuses() {
    assertThatThrownBy(() ->
            new FailedWorkItem(
                UUID.randomUUID(),
                new TenantId("aisquad"),
                TYPE,
                WorkStatus.SUCCEEDED,
                1,
                Optional.empty(),
                java.time.OffsetDateTime.now(java.time.Clock.systemUTC())))
        .isInstanceOf(IllegalArgumentException.class);
  }

  private static WorkItem item(UUID id, int attempt) {
    return new WorkItem(
        id,
        new TenantId("aisquad"),
        TYPE,
        1,
        Map.of("noteId", "n-1"),
        attempt,
        3,
        Optional.empty());
  }

  @Test
  void aPerItemAttemptLimitIsOptionalAndBetweenOneAndThePublishedMaximum() {
    EnqueueRequest plain = EnqueueRequest.of(WorkType.of("fixture.limit"), Map.of());
    int maximum = WorkItemContract.MAX_ATTEMPTS_PER_ITEM;

    assertThat(plain.maxAttempts()).isEmpty();
    assertThat(plain.withMaxAttempts(7).maxAttempts()).hasValue(7);
    assertThat(plain.withMaxAttempts(7).type()).isEqualTo(plain.type());
    assertThat(plain.withMaxAttempts(1).maxAttempts()).hasValue(1);
    assertThat(plain.withMaxAttempts(maximum).maxAttempts()).hasValue(maximum);
    assertThatThrownBy(() -> plain.withMaxAttempts(0)).isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> plain.withMaxAttempts(maximum + 1))
        .as("a producer cannot enqueue work that never becomes terminal")
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("between 1 and " + maximum);
    assertThatThrownBy(() -> plain.withMaxAttempts(WorkItemContract.UNLIMITED_ATTEMPTS))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() ->
            new EnqueueRequest(
                plain.type(), Map.of(), Optional.empty(), OptionalInt.of(maximum + 1)))
        .as("the canonical constructor enforces the same bound")
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void onlyTenantInternalSystemWorkMayRegisterWithoutAnAttemptLimit() {
    assertThat(WorkRegistration.tenantInternal(TYPE).unlimitedAttempts()).isFalse();
    assertThat(WorkRegistration.requiresAuthorization(TYPE).unlimitedAttempts()).isFalse();
    assertThat(new WorkRegistration(TYPE, true).unlimitedAttempts())
        .as("registrations written before the component was added keep the bounded limit")
        .isFalse();

    WorkRegistration unlimited = WorkRegistration.tenantInternalRetriedWithoutLimit(TYPE);
    assertThat(unlimited.unlimitedAttempts()).isTrue();
    assertThat(unlimited.tenantInternalSystemWork()).isTrue();
    assertThatThrownBy(() -> new WorkRegistration(TYPE, false, true))
        .as("work that needs authorization or has external effects always becomes terminal")
        .isInstanceOf(IllegalArgumentException.class);
  }
}
