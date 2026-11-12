package com.aisquad.owlmast.audit.api;

import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.ServiceIdentity;
import java.util.Objects;
import java.util.Optional;

/**
 * Actor of an audited mutation: a kind and either an actor id or an explicit Unknown (envelope v1).
 * Unknown is a deliberate statement by the producer, never an omission. The id follows the rule of
 * every textual envelope field: non-blank, single-line, at most {@link
 * AuditEnvelopeContract#MAX_FIELD_LENGTH} characters.
 */
public record AuditActor(ActorKind kind, Optional<String> id) {

  public AuditActor {
    Objects.requireNonNull(kind, "kind");
    Objects.requireNonNull(id, "id");
    id.ifPresent(value -> AuditIdentifiers.requireIdentifier(value, "actor id"));
  }

  public static AuditActor of(ActorKind kind, String id) {
    return new AuditActor(kind, Optional.of(id));
  }

  /** The actor's kind is known but no identity can be asserted. */
  public static AuditActor unknown(ActorKind kind) {
    return new AuditActor(kind, Optional.empty());
  }

  public static AuditActor human(PrincipalId principal) {
    return of(ActorKind.HUMAN, principal.value());
  }

  public static AuditActor agent(PrincipalId principal) {
    return of(ActorKind.AGENT, principal.value());
  }

  /** The backend acting for a tenant, as processors do. */
  public static AuditActor backendService() {
    return of(ActorKind.SERVICE, ServiceIdentity.BACKEND.value());
  }

  public boolean isUnknown() {
    return id.isEmpty();
  }
}
