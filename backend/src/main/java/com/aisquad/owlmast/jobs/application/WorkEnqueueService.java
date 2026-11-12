package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Supplier;
import reactor.core.publisher.Mono;

/**
 * Inserts the work record through the scoped transaction helper, which joins the caller's active
 * transaction with the same scope (atomic with the business change, AC1), rejects a different
 * scope, and fails closed without one. A work type no handler in this build registers is rejected
 * before the transaction opens: claims take only registered types, so such an item would stay
 * {@code PENDING} for good, never terminal and never listed. Every instance of one build registers
 * the same handlers, so the check never refuses work a peer of the same build could run. The
 * registry is resolved on first use, because handlers may themselves enqueue follow-up work. The
 * item's attempt limit is decided here and stored on the item: the request's, else the configured
 * one; only the handler's registration can lift it ({@code unlimitedAttempts}), and a request that
 * names a limit for such a type is rejected.
 */
public final class WorkEnqueueService implements WorkEnqueue {

  private final ScopedTransactions transactions;
  private final WorkRepository repository;
  private final RetryPolicy policy;
  private final Supplier<HandlerRegistry> registry;

  public WorkEnqueueService(
      ScopedTransactions transactions,
      WorkRepository repository,
      RetryPolicy policy,
      Supplier<HandlerRegistry> registry) {
    this.transactions = Objects.requireNonNull(transactions, "transactions");
    this.repository = Objects.requireNonNull(repository, "repository");
    this.policy = Objects.requireNonNull(policy, "policy");
    this.registry = Objects.requireNonNull(registry, "registry");
  }

  @Override
  public Mono<UUID> enqueue(EnqueueRequest request) {
    Objects.requireNonNull(request, "request");
    Optional<WorkHandler> handler = registry.get().find(request.type());
    if (handler.isEmpty()) {
      return Mono.error(
          new IllegalArgumentException(
              "no handler is registered for work type '" + request.type().value() + "'"));
    }
    boolean unlimited = handler.get().registration().unlimitedAttempts();
    if (unlimited && request.maxAttempts().isPresent()) {
      return Mono.error(
          new IllegalArgumentException(
              "work type '"
                  + request.type().value()
                  + "' is retried without an attempt limit; a request cannot set one"));
    }
    int maxAttempts =
        unlimited
            ? WorkItemContract.UNLIMITED_ATTEMPTS
            : request.maxAttempts().orElse(policy.maxAttempts());
    return transactions.inTransaction(scope ->
        repository.insert(
            UUID.randomUUID(), request, WorkItemContract.VERSION, maxAttempts, scope.principal()));
  }
}
