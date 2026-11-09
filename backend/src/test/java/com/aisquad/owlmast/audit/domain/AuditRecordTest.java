package com.aisquad.owlmast.audit.domain;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.audit.api.AuditEnvelope;
import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.audit.api.AuditOutcome;
import com.aisquad.owlmast.audit.api.AuditedMutation;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;

/** AC3: every reason the module writes can be read back through the envelope's own validation. */
class AuditRecordTest {

  private static final AuditedMutation<UUID> MUTATION =
      AuditedMutation.creating(
          AuditActor.of(ActorKind.HUMAN, "person-a"),
          "fixture.note",
          "note.create",
          "corr-1",
          scope -> Mono.empty());
  private static final OffsetDateTime AT =
      OffsetDateTime.of(2026, 11, 9, 0, 0, 0, 0, ZoneOffset.UTC);

  @Test
  void aBlankOrAbsentReasonBecomesAFixedCode() {
    assertThat(AuditRecord.storableReason(null)).isEqualTo(AuditRecord.REASON_UNKNOWN);
    assertThat(AuditRecord.storableReason("")).isEqualTo(AuditRecord.REASON_UNKNOWN);
    assertThat(AuditRecord.storableReason(" \n ")).isEqualTo(AuditRecord.REASON_UNKNOWN);
    assertThat(unsuccessful("").reason()).contains(AuditRecord.REASON_UNKNOWN);
  }

  @Test
  void anOverlongOrMultiLineReasonIsBroughtWithinTheEnvelopeBound() {
    String chain = "VeryLongExceptionClassNameNumberOne <- ".repeat(20);
    String stored = AuditRecord.storableReason(chain);
    assertThat(stored).hasSize(AuditEnvelopeContract.MAX_FIELD_LENGTH).startsWith("VeryLong");
    assertThat(AuditRecord.storableReason("first\nsecond\rthird")).isEqualTo("first second third");
    assertThat(AuditRecord.storableReason("IllegalStateException <- PSQLException"))
        .as("ordinary SafeFailure output is kept as is")
        .isEqualTo("IllegalStateException <- PSQLException");
  }

  @Test
  void everyStoredReasonIsAcceptedByTheEnvelopeOnRead() {
    for (String raw : new String[] {"", "x".repeat(1000), "a\nb", "IllegalStateException"}) {
      AuditRecord record = unsuccessful(raw);
      AuditEnvelope envelope =
          new AuditEnvelope(
              record.envelopeVersion(),
              record.eventId(),
              record.actor(),
              new TenantId("tenant-a"),
              record.project(),
              record.objectType(),
              record.objectId(),
              record.objectVersion(),
              record.action(),
              record.outcome(),
              record.reason(),
              record.occurredAt(),
              AT,
              record.correlationId());
      assertThat(envelope.reason()).isPresent();
    }
  }

  private static AuditRecord unsuccessful(String reason) {
    return AuditRecord.unsuccessful(UUID.randomUUID(), MUTATION, AuditOutcome.FAILED, reason, AT);
  }
}
