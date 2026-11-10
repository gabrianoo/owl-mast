package com.aisquad.owlmast.platform.persistence;

import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Function;
import lombok.NonNull;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransaction;
import org.springframework.transaction.reactive.TransactionSynchronization;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Signal;

/**
 * Opens an R2DBC transaction only when a {@link ScopeContext} is bound, and binds the tenant to the
 * actual connection/transaction through a transaction-local PostgreSQL setting (AD-5). Work runs
 * inside the transaction and sees the same scope on every asynchronous hop.
 *
 * <p>A transaction carries exactly one scope. The scope is recorded as a resource of the actual
 * Spring transaction and its lifetime is tied to that physical transaction through a registered
 * {@link TransactionSynchronization}: it is unbound when the transaction is suspended (for example
 * by {@code PROPAGATION_REQUIRES_NEW}), rebound on resume, and removed after commit or rollback. A
 * nested call that joins the same transaction with an equal scope participates without re-binding,
 * while a nested call with a different tenant or principal is rejected with {@link
 * IncompatibleScopeException} before it runs any work or touches the connection setting. The
 * rejection is recorded on the transaction and re-checked in {@code beforeCommit}, so whoever owns
 * the transaction (this helper or an external operator) cannot commit after a caught rejection: the
 * commit fails and the transaction rolls back. Calls without an actual synchronized transaction are
 * refused with {@link ScopeBindingUnavailableException} before any work.
 */
public final class ScopedTransactions {

  /** Transaction-local setting readable with {@code current_setting(name, true)}. */
  public static final String TENANT_SETTING = "owlmast.tenant_id";

  /** Key of the {@link Binding} resource attached to the active transaction. */
  static final Object SCOPE_RESOURCE = new Object();

  /**
   * Scope bound to one physical transaction, plus whether a nested call was rejected inside it.
   * Identity matters: a binding belongs to exactly one transaction lifecycle.
   */
  private static final class Binding {
    private final ScopeContext scope;
    private final AtomicBoolean poisoned = new AtomicBoolean();

    private Binding(ScopeContext scope) {
      this.scope = scope;
    }

    ScopeContext scope() {
      return scope;
    }

    AtomicBoolean poisoned() {
      return poisoned;
    }
  }

  private final TransactionalOperator transactionalOperator;
  private final DatabaseClient databaseClient;

  public ScopedTransactions(
      TransactionalOperator transactionalOperator, DatabaseClient databaseClient) {
    this.transactionalOperator =
        Objects.requireNonNull(transactionalOperator, "transactionalOperator");
    this.databaseClient = Objects.requireNonNull(databaseClient, "databaseClient");
  }

  /** Fails closed with {@code MissingScopeException} before any connection is acquired. */
  public <T> Mono<T> inTransaction(Function<ScopeContext, Mono<T>> work) {
    Objects.requireNonNull(work, "work");
    return Scopes.current()
        .flatMap(scope ->
            transactionalOperator.execute(status -> scoped(status, scope, work)).singleOrEmpty());
  }

  /** The tenant bound to the current transaction, or empty outside a scoped transaction. */
  public Mono<String> boundTenant() {
    return databaseClient
        .sql("select current_setting(:name, true) as tenant")
        .bind("name", TENANT_SETTING)
        .map(row -> Optional.ofNullable(row.get("tenant", String.class)))
        .one()
        .flatMap(Mono::justOrEmpty)
        .filter(tenant -> !tenant.isEmpty());
  }

  private <T> Mono<T> scoped(
      ReactiveTransaction status, ScopeContext scope, Function<ScopeContext, Mono<T>> work) {
    return TransactionSynchronizationManager.forCurrentTransaction()
        .flatMap(transaction -> joinOrBind(transaction, status, scope))
        .flatMap(binding ->
            Mono.defer(() -> work.apply(scope))
                .materialize()
                .flatMap(signal -> rejectIfPoisoned(binding, signal))
                .dematerialize());
  }

  private Mono<Binding> joinOrBind(
      TransactionSynchronizationManager transaction,
      ReactiveTransaction status,
      ScopeContext requested) {
    if (!transaction.isActualTransactionActive() || !transaction.isSynchronizationActive()) {
      return Mono.error(new ScopeBindingUnavailableException());
    }
    if (!transaction.hasResource(SCOPE_RESOURCE)) {
      Binding binding = new Binding(requested);
      transaction.bindResource(SCOPE_RESOURCE, binding);
      transaction.registerSynchronization(new ScopeSynchronization(transaction, binding));
      return bindTenant(requested).thenReturn(binding);
    }
    Binding bound = (Binding) transaction.getResource(SCOPE_RESOURCE);
    assert bound != null;
    if (requested.equals(bound.scope())) {
      return Mono.just(bound);
    }
    bound.poisoned().set(true);
    status.setRollbackOnly();
    return Mono.error(IncompatibleScopeException.requestedScopeDiffers());
  }

  /**
   * Ties the binding to the physical transaction: hidden while the transaction is suspended,
   * restored on resume, removed after completion, and enforced at the real commit boundary.
   */
  private record ScopeSynchronization(
      TransactionSynchronizationManager transaction, Binding binding)
      implements TransactionSynchronization {

    @Override
    public @NonNull Mono<Void> suspend() {
      return Mono.fromRunnable(this::unbindIfOwned);
    }

    @Override
    public @NonNull Mono<Void> resume() {
      return Mono.fromRunnable(() -> {
        if (!transaction.hasResource(SCOPE_RESOURCE)) {
          transaction.bindResource(SCOPE_RESOURCE, binding);
        }
      });
    }

    @Override
    public @NonNull Mono<Void> beforeCommit(boolean readOnly) {
      return binding.poisoned().get()
          ? Mono.error(IncompatibleScopeException.transactionPoisoned())
          : Mono.empty();
    }

    @Override
    public @NonNull Mono<Void> afterCompletion(int status) {
      return Mono.fromRunnable(this::unbindIfOwned);
    }

    private void unbindIfOwned() {
      if (transaction.hasResource(SCOPE_RESOURCE)
          && transaction.getResource(SCOPE_RESOURCE) == binding) {
        transaction.unbindResource(SCOPE_RESOURCE);
      }
    }
  }

  /**
   * A Mono materializes as one signal: its value, or completion, or error. A poisoned transaction
   * must not surface a value or complete; an error already rolls back and keeps its own cause.
   */
  private static <T> Mono<Signal<T>> rejectIfPoisoned(Binding binding, Signal<T> signal) {
    return !signal.isOnError() && binding.poisoned().get()
        ? Mono.error(IncompatibleScopeException.transactionPoisoned())
        : Mono.just(signal);
  }

  private Mono<Void> bindTenant(ScopeContext scope) {
    return databaseClient
        .sql("select set_config(:name, :value, true)")
        .bind("name", TENANT_SETTING)
        .bind("value", scope.tenant().value())
        .then();
  }
}
