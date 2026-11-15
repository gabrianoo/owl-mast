package com.aisquad.owlmast.access.application;

import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.access.domain.SessionEnd;
import com.aisquad.owlmast.access.port.PrincipalStore;
import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.audit.api.AuditedMutation;
import com.aisquad.owlmast.audit.api.AuditedMutations;
import com.aisquad.owlmast.audit.api.MutationOutcome;
import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.diagnostics.SafeFailure;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.platform.scope.ServiceIdentity;
import com.aisquad.owlmast.platform.scope.TenantId;
import java.util.Objects;
import java.util.Optional;
import lombok.extern.slf4j.Slf4j;
import reactor.core.publisher.Mono;

/**
 * Binds a validated identity to its principal and records what happens to browser sessions
 * (OM-02.01): sign-in, refused or failed sign-in, sign-out, and a session ended by expiry or
 * revocation. Every record goes through {@link AuditedMutations}, so it has the audit envelope's
 * guarantees and nothing but identifiers and fixed codes can reach it: no credential, token, name
 * or address.
 *
 * <p>The backend performs these steps itself, before any person's scope exists, so they run under
 * the backend's service scope for the installation's tenant. The audit actor is the person: the
 * principal for a session that exists, an explicit Unknown for a sign-in that bound nobody. For an
 * expiry or a revocation the actor is the person whose session ended; who ended it at the identity
 * provider is in the provider's own event log.
 */
@Slf4j
public final class SessionLedger {

  static final String SESSION = "session";
  static final String CREDENTIAL = "credential";
  static final String SIGN_IN = "session.sign-in";
  static final String VERIFY = "credential.verify";
  static final String SIGNED_IN_VERSION = "signed-in";
  static final String ENDED_VERSION = "ended";

  private final AuditedMutations mutations;
  private final ScopedTransactions transactions;
  private final PrincipalStore principals;
  private final ScopeContext serviceScope;

  public SessionLedger(
      AuditedMutations mutations,
      ScopedTransactions transactions,
      PrincipalStore principals,
      TenantId tenant) {
    this.mutations = Objects.requireNonNull(mutations, "mutations");
    this.transactions = Objects.requireNonNull(transactions, "transactions");
    this.principals = Objects.requireNonNull(principals, "principals");
    this.serviceScope = ServiceIdentity.backendScope(Objects.requireNonNull(tenant, "tenant"));
  }

  /** The tenant every signed-in principal acts in until OM-02.02 supplies membership. */
  public TenantId tenant() {
    return serviceScope.tenant();
  }

  /** The principal of this identity, created on first use; nothing is recorded as an outcome. */
  public Mono<PrincipalId> principalOf(ExternalIdentity identity) {
    Objects.requireNonNull(identity, "identity");
    return transactions
        .inTransaction(scope -> principals.bind(identity))
        .contextWrite(Scopes.bind(serviceScope));
  }

  /**
   * A completed sign-in: binds the principal and records the outcome with the business change. An
   * error means no session may be created: the caller fails the sign-in.
   */
  public Mono<PrincipalId> signedIn(ExternalIdentity identity, String sessionRef) {
    return principalOf(identity)
        .flatMap(principal ->
            mutations
                .execute(
                    AuditedMutation.<PrincipalId>changing(
                        AuditActor.human(principal),
                        SESSION,
                        sessionRef,
                        SIGN_IN,
                        sessionRef,
                        scope ->
                            principals
                                .recordSignIn(principal)
                                .map(count ->
                                    new MutationOutcome<>(
                                        principal, sessionRef, SIGNED_IN_VERSION))))
                .map(result -> result.value())
                .contextWrite(Scopes.bind(serviceScope)));
  }

  /**
   * A sign-in that bound nobody because the credential or the answer was refused. {@code
   * reasonCode} is one of this module's fixed codes. Never fails: a record that cannot be written
   * leaves a safe log line.
   */
  public Mono<Void> signInRefused(String reasonCode, String correlationId) {
    return unsuccessful(SESSION, SIGN_IN, correlationId, new OperationDeniedException(reasonCode));
  }

  /** A sign-in that could not be completed because the identity provider or a store failed. */
  public Mono<Void> signInFailed(Throwable failure, String correlationId) {
    return unsuccessful(SESSION, SIGN_IN, correlationId, failure);
  }

  /** A presented credential that was refused; no principal was bound. */
  public Mono<Void> credentialRefused(String reasonCode, String correlationId) {
    return unsuccessful(
        CREDENTIAL, VERIFY, correlationId, new OperationDeniedException(reasonCode));
  }

  /** A session that ended. Never fails: the session is gone whether or not the record lands. */
  public Mono<Void> ended(PrincipalId principal, String sessionRef, SessionEnd end) {
    return mutations
        .execute(
            AuditedMutation.<String>changing(
                AuditActor.human(principal),
                SESSION,
                sessionRef,
                end.action(),
                sessionRef,
                scope -> Mono.just(new MutationOutcome<>(sessionRef, sessionRef, ENDED_VERSION))))
        .contextWrite(Scopes.bind(serviceScope))
        .then()
        .onErrorResume(failure -> {
          log.error(
              "Session outcome {} for session {} was not recorded: {}",
              end.action(),
              sessionRef,
              SafeFailure.describe(failure));
          return Mono.empty();
        });
  }

  private Mono<Void> unsuccessful(
      String objectType, String action, String correlationId, Throwable outcome) {
    // The business function fails on purpose: an audited mutation records a failure as FAILED and
    // an OperationDeniedException as DENIED through its separate outcome path, then signals the
    // same error again, which is the expected end here.
    return mutations
        .execute(
            new AuditedMutation<String>(
                AuditActor.unknown(ActorKind.HUMAN),
                Optional.empty(),
                objectType,
                Optional.empty(),
                action,
                correlationId,
                scope -> Mono.error(outcome)))
        .contextWrite(Scopes.bind(serviceScope))
        .then()
        .onErrorResume(failure -> {
          if (!failure.equals(outcome)) {
            log.error(
                "Outcome of {} ({}) was not recorded: {}",
                action,
                correlationId,
                SafeFailure.describe(failure));
          }
          return Mono.empty();
        });
  }
}
