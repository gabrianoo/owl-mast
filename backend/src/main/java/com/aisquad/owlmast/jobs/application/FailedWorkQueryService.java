package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.FailedWorkItem;
import com.aisquad.owlmast.jobs.api.FailedWorkQuery;
import com.aisquad.owlmast.jobs.port.WorkRepository;
import com.aisquad.owlmast.platform.persistence.ScopedTransactions;
import java.util.Objects;
import reactor.core.publisher.Flux;

/** Tenant-scoped operator listing; fails closed without a bound scope (AC5). */
public final class FailedWorkQueryService implements FailedWorkQuery {

  static final int MAX_LIMIT = 1000;

  private final ScopedTransactions transactions;
  private final WorkRepository repository;

  public FailedWorkQueryService(ScopedTransactions transactions, WorkRepository repository) {
    this.transactions = Objects.requireNonNull(transactions, "transactions");
    this.repository = Objects.requireNonNull(repository, "repository");
  }

  @Override
  public Flux<FailedWorkItem> listTerminalFailures(int limit) {
    if (limit < 1 || limit > MAX_LIMIT) {
      return Flux.error(new IllegalArgumentException("limit must be between 1 and " + MAX_LIMIT));
    }
    return transactions
        .inTransaction(scope -> repository.listTerminalFailures(limit).collectList())
        .flatMapMany(Flux::fromIterable);
  }
}
