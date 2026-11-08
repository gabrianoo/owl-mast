package com.aisquad.owlmast.audit.api;

import com.aisquad.owlmast.platform.scope.ScopeContext;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import reactor.core.publisher.Mono;

/**
 * A covered mutation (AC3): the envelope fields the caller knows up front and the business function
 * that performs the change inside the scoped transaction. The tenant comes from the bound scope;
 * {@code objectId} may be absent when the object does not exist yet (the outcome supplies it). The
 * business function must not catch and hide its own failures: an error rolls the transaction back
 * and is recorded through the separate outcome path.
 */
public record AuditedMutation<T>(
    AuditActor actor,
    Optional<String> project,
    String objectType,
    Optional<String> objectId,
    String action,
    String correlationId,
    Function<ScopeContext, Mono<MutationOutcome<T>>> business) {

  public AuditedMutation {
    Objects.requireNonNull(actor, "actor");
    Objects.requireNonNull(project, "project");
    AuditIdentifiers.requireIdentifier(objectType, "object type");
    Objects.requireNonNull(objectId, "objectId");
    AuditIdentifiers.requireIdentifier(action, "action");
    AuditIdentifiers.requireCorrelationId(correlationId);
    Objects.requireNonNull(business, "business");
    project.ifPresent(value -> AuditIdentifiers.requireIdentifier(value, "project"));
    objectId.ifPresent(value -> AuditIdentifiers.requireIdentifier(value, "object id"));
  }

  /** A mutation creating a new object under explicit Unknown project (pre-OM-02.02). */
  public static <T> AuditedMutation<T> creating(
      AuditActor actor,
      String objectType,
      String action,
      String correlationId,
      Function<ScopeContext, Mono<MutationOutcome<T>>> business) {
    return new AuditedMutation<>(
        actor, Optional.empty(), objectType, Optional.empty(), action, correlationId, business);
  }

  /** A mutation of an existing object under explicit Unknown project (pre-OM-02.02). */
  public static <T> AuditedMutation<T> changing(
      AuditActor actor,
      String objectType,
      String objectId,
      String action,
      String correlationId,
      Function<ScopeContext, Mono<MutationOutcome<T>>> business) {
    return new AuditedMutation<>(
        actor,
        Optional.empty(),
        objectType,
        Optional.of(objectId),
        action,
        correlationId,
        business);
  }
}
