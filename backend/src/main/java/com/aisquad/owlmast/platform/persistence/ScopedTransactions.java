package com.aisquad.owlmast.platform.persistence;

import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

/**
 * Opens an R2DBC transaction only when a {@link ScopeContext} is bound, and binds the tenant to the
 * actual connection/transaction through a transaction-local PostgreSQL setting (AD-5). Work runs
 * inside the transaction and sees the same scope on every asynchronous hop.
 */
public final class ScopedTransactions {

  /** Transaction-local setting readable with {@code current_setting(name, true)}. */
  public static final String TENANT_SETTING = "owlmast.tenant_id";

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
            transactionalOperator.transactional(
                bindTenant(scope).then(Mono.defer(() -> work.apply(scope)))));
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

  private Mono<Void> bindTenant(ScopeContext scope) {
    return databaseClient
        .sql("select set_config(:name, :value, true)")
        .bind("name", TENANT_SETTING)
        .bind("value", scope.tenant().value())
        .then();
  }
}
