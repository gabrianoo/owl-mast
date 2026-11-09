package com.aisquad.owlmast.audit.adapter.persistence;

import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.audit.api.AuditEnvelope;
import com.aisquad.owlmast.audit.api.AuditOutcome;
import com.aisquad.owlmast.audit.domain.AuditRecord;
import com.aisquad.owlmast.audit.port.AuditStore;
import com.aisquad.owlmast.jobs.api.NonRetryableWorkException;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.TenantId;
import io.r2dbc.spi.Readable;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.r2dbc.core.DatabaseClient.GenericExecuteSpec;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * Audit-owned tables {@code audit.publication_intent} and {@code audit.event} (V003). Every
 * statement filters on the tenant bound to the transaction; every history insert (publication and
 * separate outcome) is keyed on the event id, so a repeated or overlapping write is a no-op, except
 * that publication corrects an unsuccessful outcome for an execution that did commit.
 */
@Repository
@RequiredArgsConstructor
class R2dbcAuditStore implements AuditStore {

  private static final String BOUND_TENANT =
      "current_setting('" + ScopedTransactions.TENANT_SETTING + "', true)";
  private static final String ENVELOPE_COLUMNS =
      "event_id, envelope_version, tenant_id, actor_kind, actor_id, project_id, object_type,"
          + " object_id, object_version, action, outcome, reason, occurred_at, recorded_at,"
          + " correlation_id";

  /**
   * Publication replaces a separate-path row for the same event that is not {@code SUCCEEDED}: the
   * intent exists only because the business transaction committed, so it is the truth about that
   * execution, whatever an outcome writer concluded while the commit's result was unknown. A repeat
   * publication (an existing {@code SUCCEEDED} row) is kept unchanged.
   */
  private static final String CORRECT_UNSUCCESSFUL =
      " on conflict (event_id) do update set envelope_version = excluded.envelope_version,"
          + " actor_kind = excluded.actor_kind, actor_id = excluded.actor_id,"
          + " project_id = excluded.project_id, object_type = excluded.object_type,"
          + " object_id = excluded.object_id, object_version = excluded.object_version,"
          + " action = excluded.action, outcome = excluded.outcome, reason = excluded.reason,"
          + " occurred_at = excluded.occurred_at, recorded_at = excluded.recorded_at,"
          + " correlation_id = excluded.correlation_id, published_at = now()"
          + " where audit.event.outcome <> 'SUCCEEDED' and audit.event.tenant_id = excluded.tenant_id";

  private final DatabaseClient databaseClient;

  @Override
  public Mono<Void> recordIntent(AuditRecord record) {
    return insert("audit.publication_intent", record, "");
  }

  @Override
  public Mono<Void> recordOutcome(AuditRecord record) {
    return insert("audit.event", record, " on conflict (event_id) do nothing");
  }

  @Override
  public Mono<Long> publish(UUID eventId) {
    Mono<Long> inserted =
        databaseClient
            .sql(
                "insert into audit.event ("
                    + ENVELOPE_COLUMNS
                    + ") select "
                    + ENVELOPE_COLUMNS
                    + " from audit.publication_intent where event_id = :eventId and tenant_id = "
                    + BOUND_TENANT
                    + CORRECT_UNSUCCESSFUL)
            .bind("eventId", eventId)
            .fetch()
            .rowsUpdated();
    Mono<Long> marked =
        databaseClient
            .sql(
                "update audit.publication_intent set published_at = coalesce(published_at, now())"
                    + " where event_id = :eventId and tenant_id = "
                    + BOUND_TENANT)
            .bind("eventId", eventId)
            .fetch()
            .rowsUpdated();
    return inserted.flatMap(rows ->
        marked.flatMap(found ->
            found == 1 ? Mono.just(rows) : Mono.error(new MissingIntentException(eventId))));
  }

  @Override
  public Mono<AuditEnvelope> find(UUID eventId) {
    return databaseClient
        .sql(
            "select "
                + ENVELOPE_COLUMNS
                + " from audit.event where event_id = :eventId and tenant_id = "
                + BOUND_TENANT)
        .bind("eventId", eventId)
        .map(R2dbcAuditStore::toEnvelope)
        .one();
  }

  @Override
  public Flux<AuditEnvelope> listByObject(String objectType, String objectId, int limit) {
    return databaseClient
        .sql(
            "select "
                + ENVELOPE_COLUMNS
                + " from audit.event where tenant_id = "
                + BOUND_TENANT
                + " and object_type = :objectType and object_id = :objectId"
                + " order by occurred_at desc, event_id limit :limit")
        .bind("objectType", objectType)
        .bind("objectId", objectId)
        .bind("limit", (long) limit)
        .map(R2dbcAuditStore::toEnvelope)
        .all();
  }

  @Override
  public Mono<Long> countUnpublishedIntents() {
    return databaseClient
        .sql(
            "select count(*) as pending from audit.publication_intent where tenant_id = "
                + BOUND_TENANT
                + " and published_at is null")
        .map(row -> row.get("pending", Long.class))
        .one();
  }

  private Mono<Void> insert(String table, AuditRecord record, String conflictClause) {
    GenericExecuteSpec spec =
        databaseClient
            .sql(
                "insert into "
                    + table
                    + " ("
                    + ENVELOPE_COLUMNS
                    + ") values (:eventId, :version, "
                    + BOUND_TENANT
                    + ", :actorKind, :actorId, :projectId, :objectType, :objectId,"
                    + " :objectVersion, :action, :outcome, :reason, :occurredAt, now(),"
                    + " :correlationId)"
                    + conflictClause)
            .bind("eventId", record.eventId())
            .bind("version", record.envelopeVersion())
            .bind("actorKind", record.actor().kind().name())
            .bind("objectType", record.objectType())
            .bind("action", record.action())
            .bind("outcome", record.outcome().name())
            .bind("occurredAt", record.occurredAt())
            .bind("correlationId", record.correlationId());
    spec = bindOptional(spec, "actorId", record.actor().id());
    spec = bindOptional(spec, "projectId", record.project());
    spec = bindOptional(spec, "objectId", record.objectId());
    spec = bindOptional(spec, "objectVersion", record.objectVersion());
    spec = bindOptional(spec, "reason", record.reason());
    return spec.fetch().rowsUpdated().then();
  }

  private static AuditEnvelope toEnvelope(Readable row) {
    return new AuditEnvelope(
        row.get("envelope_version", Integer.class),
        row.get("event_id", UUID.class),
        new AuditActor(
            ActorKind.valueOf(row.get("actor_kind", String.class)),
            Optional.ofNullable(row.get("actor_id", String.class))),
        new TenantId(row.get("tenant_id", String.class)),
        Optional.ofNullable(row.get("project_id", String.class)),
        row.get("object_type", String.class),
        Optional.ofNullable(row.get("object_id", String.class)),
        Optional.ofNullable(row.get("object_version", String.class)),
        row.get("action", String.class),
        AuditOutcome.valueOf(row.get("outcome", String.class)),
        Optional.ofNullable(row.get("reason", String.class)),
        row.get("occurred_at", OffsetDateTime.class),
        row.get("recorded_at", OffsetDateTime.class),
        row.get("correlation_id", String.class));
  }

  private static GenericExecuteSpec bindOptional(
      GenericExecuteSpec spec, String name, Optional<String> value) {
    return value.map(v -> spec.bind(name, v)).orElseGet(() -> spec.bindNull(name, String.class));
  }

  /**
   * The publish item names an intent the bound tenant does not have. Intent and item commit
   * together, so no retry can make the intent appear: the attempt is non-retryable and the item
   * fails terminally. Only the class is persisted.
   */
  static final class MissingIntentException extends NonRetryableWorkException {
    private static final long serialVersionUID = 1L;

    MissingIntentException(UUID eventId) {
      super("No publication intent for event " + eventId + " in the bound tenant");
    }
  }
}
