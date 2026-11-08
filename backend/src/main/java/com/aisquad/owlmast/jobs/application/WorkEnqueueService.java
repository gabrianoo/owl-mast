package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.EnqueueRequest;
import com.aisquad.owlmast.jobs.api.WorkEnqueue;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.domain.RetryPolicy;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.util.Objects;
import java.util.UUID;
import reactor.core.publisher.Mono;

/**
 * Inserts the work record through the scoped transaction helper, which joins the caller's active
 * transaction with the same scope (atomic with the business change, AC1), rejects a different
 * scope, and fails closed without one.
 */
public final class WorkEnqueueService implements WorkEnqueue {

  private final ScopedTransactions transactions;
  private final WorkRepository repository;
  private final RetryPolicy policy;

  public WorkEnqueueService(
      ScopedTransactions transactions, WorkRepository repository, RetryPolicy policy) {
    this.transactions = Objects.requireNonNull(transactions, "transactions");
    this.repository = Objects.requireNonNull(repository, "repository");
    this.policy = Objects.requireNonNull(policy, "policy");
  }

  @Override
  public Mono<UUID> enqueue(EnqueueRequest request) {
    Objects.requireNonNull(request, "request");
    return transactions.inTransaction(scope ->
        repository.insert(
            UUID.randomUUID(),
            request,
            WorkItemContract.VERSION,
            request.maxAttempts().orElse(policy.maxAttempts()),
            scope.principal()));
  }
}
