package com.aisquad.owlmast.platform.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.platform.scope.MissingScopeException;
import io.r2dbc.spi.ConnectionFactories;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.reactivestreams.Publisher;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.reactive.TransactionCallback;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

/** Database-free check that a missing scope never reaches the transaction or the connection. */
class ScopedTransactionsTest {

  @Test
  void absentScopeFailsBeforeAnyTransactionOrWork() {
    AtomicBoolean transactionOpened = new AtomicBoolean();
    AtomicBoolean workInvoked = new AtomicBoolean();
    TransactionalOperator recordingOperator =
        new TransactionalOperator() {
          @Override
          public <T> Flux<T> execute(TransactionCallback<T> action) {
            transactionOpened.set(true);
            return Flux.error(new AssertionError("must not open a transaction"));
          }

          @Override
          public <T> Flux<T> transactional(Flux<T> flux) {
            transactionOpened.set(true);
            return flux;
          }

          @Override
          public <T> Mono<T> transactional(Mono<T> mono) {
            transactionOpened.set(true);
            return mono;
          }
        };
    DatabaseClient unreachable =
        DatabaseClient.create(
            ConnectionFactories.get("r2dbc:postgresql://nobody@127.0.0.1:1/unreachable"));
    ScopedTransactions transactions = new ScopedTransactions(recordingOperator, unreachable);

    Publisher<String> flow =
        transactions.inTransaction(scope -> {
          workInvoked.set(true);
          return Mono.just("never");
        });

    StepVerifier.create(flow).expectError(MissingScopeException.class).verify();
    assertThat(transactionOpened).isFalse();
    assertThat(workInvoked).isFalse();
  }
}
