package com.aisquad.owlmast.platform.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.platform.blocking.BoundedBlocking;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

/**
 * AC3: scope stays explicit across async hops and is bound to the real transaction; commits,
 * rollbacks and the fail-closed path behave on the actual database.
 */
@SpringBootTest
@Import(ContainersConfiguration.class)
class ScopedTransactionsIT {

  private static final String PROBE = "it_scoped_tx_probe";

  @Autowired private DatabaseClient databaseClient;
  @Autowired private ScopedTransactions transactions;
  @Autowired private BoundedBlocking blocking;

  @BeforeEach
  void createProbeTable() {
    databaseClient
        .sql("create table if not exists " + PROBE + " (tenant text not null, note text not null)")
        .then()
        .block();
    databaseClient.sql("delete from " + PROBE).then().block();
  }

  @AfterEach
  void dropProbeTable() {
    databaseClient.sql("drop table if exists " + PROBE).then().block();
  }

  @Test
  void commitsWithTenantBoundToTheTransactionAcrossAsynchronousHops() {
    ScopeContext scope = ScopeContext.of("aisquad", "person-1");

    Mono<String> flow =
        transactions
            .inTransaction(current ->
                insert(current, "first")
                    .publishOn(Schedulers.parallel())
                    .then(blocking.call("legacy-sdk", () -> current.tenant().value()))
                    .flatMap(tenant -> insert(current, "after-" + tenant))
                    .then(transactions.boundTenant()))
            .contextWrite(Scopes.bind(scope));

    StepVerifier.create(flow).expectNext("aisquad").verifyComplete();
    assertThat(notes()).containsExactly("after-aisquad", "first");
    StepVerifier.create(transactions.boundTenant()).verifyComplete();
  }

  @Test
  void rollsBackEverythingWhenTheWorkFails() {
    Mono<String> flow =
        transactions
            .inTransaction(current ->
                insert(current, "doomed")
                    .then(Mono.<String>error(new IllegalStateException("downstream failure"))))
            .contextWrite(Scopes.bind(ScopeContext.of("aisquad", "person-1")));

    StepVerifier.create(flow).expectErrorMessage("downstream failure").verify();
    assertThat(notes()).isEmpty();
  }

  @Test
  void absentScopeFailsClosedWithoutTouchingTheDatabase() {
    AtomicBoolean workInvoked = new AtomicBoolean();

    Mono<String> flow =
        transactions.inTransaction(current -> {
          workInvoked.set(true);
          return insert(current, "unscoped").thenReturn("unscoped");
        });

    StepVerifier.create(flow).expectError(MissingScopeException.class).verify();
    assertThat(workInvoked).isFalse();
    assertThat(notes()).isEmpty();
  }

  @Test
  void concurrentTransactionsKeepTheirOwnTenant() {
    Mono<String> first = tenantSeenInside(ScopeContext.of("tenant-a", "person-a"));
    Mono<String> second = tenantSeenInside(ScopeContext.of("tenant-b", "person-b"));

    StepVerifier.create(Mono.zip(first, second).map(pair -> pair.getT1() + "," + pair.getT2()))
        .expectNext("tenant-a,tenant-b")
        .verifyComplete();
  }

  private Mono<String> tenantSeenInside(ScopeContext scope) {
    return transactions
        .inTransaction(current ->
            Mono.delay(java.time.Duration.ofMillis(50))
                .publishOn(Schedulers.boundedElastic())
                .then(transactions.boundTenant()))
        .contextWrite(Scopes.bind(scope));
  }

  private Mono<Void> insert(ScopeContext scope, String note) {
    return databaseClient
        .sql("insert into " + PROBE + " (tenant, note) values (:tenant, :note)")
        .bind("tenant", scope.tenant().value())
        .bind("note", note)
        .then();
  }

  private java.util.List<String> notes() {
    return databaseClient
        .sql("select note from " + PROBE + " order by note")
        .map(row -> row.get("note", String.class))
        .all()
        .collectList()
        .block();
  }
}
