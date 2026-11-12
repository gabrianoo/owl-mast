package com.aisquad.owlmast.audit.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.audit.domain.AuditRecord;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.scope.ServiceIdentity;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.lang.reflect.RecordComponent;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;

/** AC3/AC9: the envelope has the contract's fields, no payload, and bounded safe values only. */
class AuditContractTypesTest {

  private static final OffsetDateTime NOW = OffsetDateTime.now(Clock.systemUTC());

  @Test
  void envelopeHasNoFreeFormPayloadComponent() {
    assertThat(
            Arrays.stream(AuditEnvelope.class.getRecordComponents()).map(RecordComponent::getName))
        .containsExactly(
            "envelopeVersion",
            "eventId",
            "actor",
            "tenant",
            "project",
            "objectType",
            "objectId",
            "objectVersion",
            "action",
            "outcome",
            "reason",
            "occurredAt",
            "recordedAt",
            "correlationId")
        .noneMatch(name ->
            name.toLowerCase(java.util.Locale.ROOT)
                .matches(".*(payload|details|data|body|content).*"));
  }

  @Test
  void envelopeFieldsAreBoundedSingleLineIdentifiers() {
    assertThatThrownBy(() -> envelope("note", "created\nwith secret"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("single line");
    assertThatThrownBy(() -> envelope("x".repeat(257), "created"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("256");
    assertThatThrownBy(() -> envelope(" ", "created")).isInstanceOf(IllegalArgumentException.class);
    assertThat(envelope("note", "created").project()).as("explicit Unknown project").isEmpty();
  }

  @Test
  void actorsAreExplicitAboutUnknownIdentity() {
    assertThat(AuditActor.unknown(ActorKind.AGENT).isUnknown()).isTrue();
    assertThat(AuditActor.backendService())
        .isEqualTo(AuditActor.of(ActorKind.SERVICE, ServiceIdentity.BACKEND.value()));
    assertThatThrownBy(() -> AuditActor.of(ActorKind.HUMAN, " "))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void anActorIdFollowsTheRuleOfEveryTextualEnvelopeField() {
    for (String forged : new String[] {"person-a\nouter line", "person-a\rother", "a\r\nb"}) {
      assertThatThrownBy(() -> AuditActor.of(ActorKind.HUMAN, forged))
          .as("a multi-line actor id could forge lines in a rendered history")
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("single line");
    }
    String atTheBound = "p".repeat(AuditEnvelopeContract.MAX_FIELD_LENGTH);
    assertThat(AuditActor.of(ActorKind.AGENT, atTheBound).id()).contains(atTheBound);
    assertThatThrownBy(() -> AuditActor.of(ActorKind.AGENT, atTheBound + "p"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining(Integer.toString(AuditEnvelopeContract.MAX_FIELD_LENGTH));
  }

  @Test
  void outcomeVocabularyMatchesTheContract() {
    assertThat(AuditOutcome.values())
        .extracting(Enum::name)
        .containsExactly("REQUESTED", "SUCCEEDED", "FAILED", "DENIED", "UNRESOLVED");
    assertThat(ActorKind.values())
        .extracting(Enum::name)
        .containsExactly("HUMAN", "AGENT", "SERVICE", "SYSTEM");
    assertThat(AuditOutcome.FAILED.separateOutcomePath()).isTrue();
    assertThat(AuditOutcome.DENIED.separateOutcomePath()).isTrue();
    assertThat(AuditOutcome.SUCCEEDED.separateOutcomePath()).isFalse();
  }

  @Test
  void unsuccessfulRecordsKeepTheRequestedObjectAndNoVersion() {
    AuditedMutation<String> mutation =
        AuditedMutation.changing(
            AuditActor.unknown(ActorKind.HUMAN),
            "note",
            "n-1",
            "note.update",
            "corr-1",
            scope -> Mono.just(new MutationOutcome<>("ok", "n-1", "2")));
    UUID eventId = UUID.randomUUID();

    AuditRecord failed =
        AuditRecord.unsuccessful(
            eventId, mutation, AuditOutcome.FAILED, "IllegalStateException", NOW);
    assertThat(failed.objectId()).contains("n-1");
    assertThat(failed.objectVersion()).isEmpty();
    assertThat(failed.reason()).contains("IllegalStateException");
    assertThat(failed.envelopeVersion()).isEqualTo(AuditEnvelopeContract.VERSION);

    AuditRecord succeeded =
        AuditRecord.succeeded(eventId, mutation, new MutationOutcome<>("ok", "n-1", "2"), NOW);
    assertThat(succeeded.objectVersion()).contains("2");
    assertThat(succeeded.reason()).isEmpty();
    assertThatThrownBy(
            () -> AuditRecord.unsuccessful(eventId, mutation, AuditOutcome.SUCCEEDED, "x", NOW))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void correlationIdsAreValidatedUpFrontAgainstTheSharedBound() {
    String atLimit = "c".repeat(WorkItemContract.MAX_CORRELATION_ID_LENGTH);
    assertThat(AuditIdentifiers.MAX_LENGTH).isEqualTo(WorkItemContract.MAX_CORRELATION_ID_LENGTH);
    assertThat(mutation(atLimit).correlationId()).isEqualTo(atLimit);
    assertThatThrownBy(() -> mutation(atLimit + "x"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("correlation id");
    assertThatThrownBy(() -> mutation(" "))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("correlation id");
  }

  private static AuditedMutation<String> mutation(String correlationId) {
    return AuditedMutation.creating(
        AuditActor.unknown(ActorKind.SYSTEM),
        "note",
        "note.create",
        correlationId,
        scope -> Mono.just(new MutationOutcome<>("ok", "n-1", "1")));
  }

  @Test
  void denialReasonsAreCodesNeverRequestData() {
    assertThat(new OperationDeniedException("not-permitted").reasonCode())
        .isEqualTo("not-permitted");
    assertThatThrownBy(() -> new OperationDeniedException("user typed: s3cr3t"))
        .isInstanceOf(IllegalArgumentException.class);
  }

  private static AuditEnvelope envelope(String objectType, String action) {
    return new AuditEnvelope(
        1,
        UUID.randomUUID(),
        AuditActor.of(ActorKind.HUMAN, "person-1"),
        new TenantId("aisquad"),
        Optional.empty(),
        objectType,
        Optional.of("n-1"),
        Optional.of("1"),
        action,
        AuditOutcome.SUCCEEDED,
        Optional.empty(),
        NOW,
        NOW,
        "corr-1");
  }
}
