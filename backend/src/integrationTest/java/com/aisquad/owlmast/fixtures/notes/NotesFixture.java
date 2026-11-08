package com.aisquad.owlmast.fixtures.notes;

import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.audit.api.AuditedMutation;
import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.audit.api.AuditedResult;
import com.aisquad.owlmast.audit.api.MutationOutcome;
import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkType;
import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

/**
 * Test-owned fixture module (AC1, AC3): owns the table {@code fixture_notes}, changes its own
 * business row and uses only the published jobs and audit owner APIs. Failure modes let tests roll
 * back before or after the enqueue call and plant a secret into the failure message.
 */
public final class NotesFixture {

  public static final String TABLE = "fixture_notes";
  public static final String OBJECT_TYPE = "fixture.note";
  public static final String CREATE_ACTION = "note.create";

  /** Where the scoped transaction fails, if at all. */
  public enum Failure {
    NONE,
    BEFORE_ENQUEUE,
    AFTER_ENQUEUE
  }

  /** How the covered mutation ends. */
  public enum AuditedMode {
    SUCCEED,
    FAIL_AFTER_WRITE,
    DENY
  }

  private final DatabaseClient databaseClient;
  private final ScopedTransactions transactions;
  private final WorkEnqueue enqueue;
  private final AuditedMutations audited;

  public NotesFixture(
      DatabaseClient databaseClient,
      ScopedTransactions transactions,
      WorkEnqueue enqueue,
      AuditedMutations audited) {
    this.databaseClient = databaseClient;
    this.transactions = transactions;
    this.enqueue = enqueue;
    this.audited = audited;
  }

  public Mono<Void> ensureTable() {
    return databaseClient
        .sql(
            "create table if not exists "
                + TABLE
                + " (id uuid primary key, tenant_id text not null, body text not null)")
        .then();
  }

  /** Business row plus follow-up work in one scoped transaction, failing where asked. */
  public Mono<UUID> createWithFollowUp(String body, Failure failure) {
    UUID noteId = UUID.randomUUID();
    return transactions.inTransaction(scope ->
        insert(scope, noteId, body)
            .then(failAt(failure, Failure.BEFORE_ENQUEUE, body))
            .then(
                enqueue.enqueue(
                    EnqueueRequest.of(
                        FollowUpHandler.TYPE,
                        Map.of("noteId", noteId.toString()),
                        "note:" + noteId)))
            .then(failAt(failure, Failure.AFTER_ENQUEUE, body))
            .thenReturn(noteId));
  }

  /** Work without a business row, for handler-level scenarios. */
  public Mono<UUID> enqueueOnly(WorkType type, Map<String, String> payload) {
    return transactions.inTransaction(scope -> enqueue.enqueue(EnqueueRequest.of(type, payload)));
  }

  /** A covered mutation creating a note; the body is the business input a secret may hide in. */
  public Mono<AuditedResult<UUID>> auditedCreate(
      String body, AuditActor actor, String correlationId, AuditedMode mode) {
    UUID noteId = UUID.randomUUID();
    return audited.execute(
        AuditedMutation.creating(
            actor,
            OBJECT_TYPE,
            CREATE_ACTION,
            correlationId,
            scope -> insert(scope, noteId, body).then(outcomeFor(mode, noteId, body))));
  }

  public Mono<List<UUID>> noteIds() {
    return databaseClient
        .sql("select id from " + TABLE + " order by id")
        .map(row -> row.get("id", UUID.class))
        .all()
        .collectList();
  }

  public Mono<List<String>> bodies() {
    return databaseClient
        .sql("select body from " + TABLE)
        .map(row -> row.get("body", String.class))
        .all()
        .collectList();
  }

  private Mono<Void> insert(ScopeContext scope, UUID noteId, String body) {
    return databaseClient
        .sql("insert into " + TABLE + " (id, tenant_id, body) values (:id, :tenant, :body)")
        .bind("id", noteId)
        .bind("tenant", scope.tenant().value())
        .bind("body", body)
        .then();
  }

  private static Mono<Void> failAt(Failure requested, Failure here, String body) {
    return requested == here
        ? Mono.error(new IllegalStateException("fixture failure " + here + " with input " + body))
        : Mono.empty();
  }

  private static Mono<MutationOutcome<UUID>> outcomeFor(
      AuditedMode mode, UUID noteId, String body) {
    return switch (mode) {
      case SUCCEED -> Mono.just(new MutationOutcome<>(noteId, noteId.toString(), "1"));
      case FAIL_AFTER_WRITE ->
          Mono.error(new IllegalStateException("fixture failure with input " + body));
      case DENY -> Mono.error(new OperationDeniedException("fixture-denied"));
    };
  }
}
