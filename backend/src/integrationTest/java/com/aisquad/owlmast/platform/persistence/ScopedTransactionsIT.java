package com.aisquad.owlmast.platform.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.platform.blocking.BoundedBlocking;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.ContainersConfiguration;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

/**
 * AC3: scope stays explicit across async hops and is bound to the real transaction; commits,
 * rollbacks and the fail-closed path behave on the actual database.
 */
@SpringBootTest
@Import({ContainersConfiguration.class, StubIdentityConfiguration.class})
class ScopedTransactionsIT {

  private static final String PROBE = "it_scoped_tx_probe";

  @Autowired private DatabaseClient databaseClient;
  @Autowired private ScopedTransactions transactions;
  @Autowired private BoundedBlocking blocking;
  @Autowired private ReactiveTransactionManager transactionManager;
  @Autowired private TransactionalOperator transactionalOperator;

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

  @Test
  void sameScopeNestingJoinsTheSameTransactionAndKeepsTheBinding() {
    ScopeContext scope = ScopeContext.of("aisquad", "person-1");

    Mono<String> flow =
        transactions
            .inTransaction(outer ->
                insert(outer, "outer")
                    .then(backendPid())
                    .flatMap(outerPid ->
                        transactions
                            .inTransaction(inner ->
                                insert(inner, "inner")
                                    .then(backendPid())
                                    .map(innerPid -> assertSameConnection(outerPid, innerPid))
                                    .then(transactions.boundTenant()))
                            .contextWrite(Scopes.bind(scope)))
                    .flatMap(
                        innerTenant -> transactions.boundTenant().map(t -> innerTenant + "/" + t)))
            .contextWrite(Scopes.bind(scope));

    StepVerifier.create(flow).expectNext("aisquad/aisquad").verifyComplete();
    assertThat(notes()).containsExactly("inner", "outer");
  }

  @Test
  void nestedTransactionWithAnotherTenantIsRejectedBeforeAnyEffectAndRollsBack() {
    AtomicInteger innerInvocations = new AtomicInteger();

    Mono<String> flow =
        transactions
            .inTransaction(outer ->
                insert(outer, "outer-before")
                    .then(
                        transactions
                            .inTransaction(inner -> {
                              innerInvocations.incrementAndGet();
                              return insert(inner, "inner").thenReturn("inner");
                            })
                            .contextWrite(Scopes.bind(ScopeContext.of("tenant-b", "person-b")))))
            .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")));

    StepVerifier.create(flow).expectError(IncompatibleScopeException.class).verify();
    assertThat(innerInvocations).hasValue(0);
    assertThat(notes())
        .as("outer work is rolled back, nothing commits under a confused scope")
        .isEmpty();
  }

  @Test
  void nestedTransactionWithAnotherPrincipalIsRejected() {
    AtomicBoolean innerInvoked = new AtomicBoolean();

    Mono<String> flow =
        transactions
            .inTransaction(outer ->
                transactions
                    .inTransaction(inner -> {
                      innerInvoked.set(true);
                      return Mono.just("inner");
                    })
                    .contextWrite(Scopes.bind(ScopeContext.of("aisquad", "person-2"))))
            .contextWrite(Scopes.bind(ScopeContext.of("aisquad", "person-1")));

    StepVerifier.create(flow).expectError(IncompatibleScopeException.class).verify();
    assertThat(innerInvoked).isFalse();
  }

  @Test
  void outerBindingSurvivesARejectedNestedScopeAndTheTransactionCannotCommit() {
    Mono<String> flow =
        transactions
            .inTransaction(outer ->
                insert(outer, "outer")
                    .then(
                        transactions
                            .inTransaction(inner -> transactions.boundTenant())
                            .contextWrite(Scopes.bind(ScopeContext.of("tenant-b", "person-b")))
                            .onErrorResume(
                                IncompatibleScopeException.class,
                                rejected -> transactions.boundTenant()))
                    .doOnNext(tenant -> assertThat(tenant).isEqualTo("tenant-a")))
            .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")));

    StepVerifier.create(flow)
        .expectErrorSatisfies(error ->
            assertThat(error)
                .as("a rejected nested scope poisons the shared transaction even when caught")
                .isInstanceOf(IncompatibleScopeException.class)
                .hasMessageContaining("cannot commit"))
        .verify();
    assertThat(notes()).isEmpty();
  }

  // --- Round-1 review findings R1/R2: external owners, suspension and completion lifecycle ---

  @Test
  void externalOwnerCannotCommitAfterASwallowedTenantMismatch() {
    assertExternalOwnerFailsAtCommit(ScopeContext.of("tenant-b", "person-b"));
  }

  @Test
  void externalOwnerCannotCommitAfterASwallowedPrincipalMismatch() {
    assertExternalOwnerFailsAtCommit(ScopeContext.of("tenant-a", "person-b"));
  }

  private void assertExternalOwnerFailsAtCommit(ScopeContext mismatched) {
    ScopedTransactions otherInstance =
        new ScopedTransactions(transactionalOperator, databaseClient);
    AtomicBoolean secondWorkInvoked = new AtomicBoolean();
    Mono<Void> first =
        transactions
            .inTransaction(scope -> insert(scope, "first"))
            .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")));
    Mono<Void> second =
        otherInstance
            .inTransaction(scope -> {
              secondWorkInvoked.set(true);
              return insert(scope, "second");
            })
            .contextWrite(Scopes.bind(mismatched))
            .onErrorResume(IncompatibleScopeException.class, swallowed -> Mono.empty());

    Mono<String> flow =
        transactionalOperator.transactional(first.then(second).thenReturn("success"));

    StepVerifier.create(flow)
        .expectErrorSatisfies(error ->
            assertThat(error)
                .as("the external owner's commit is refused at the real commit boundary")
                .isInstanceOf(IncompatibleScopeException.class)
                .hasMessageContaining("cannot commit"))
        .verify();
    assertThat(secondWorkInvoked).isFalse();
    assertThat(notes()).as("the first row must not persist either").isEmpty();
  }

  @Test
  void requiresNewSameScopeBindsTheNewConnectionAndRestoresTheOuter() {
    ScopeContext scope = ScopeContext.of("tenant-a", "person-a");
    ScopedTransactions independent = new ScopedTransactions(requiresNew(), databaseClient);

    Mono<String> flow =
        transactions
            .inTransaction(outer ->
                backendPid()
                    .flatMap(outerPid ->
                        independent
                            .inTransaction(inner ->
                                backendPid()
                                    .doOnNext(
                                        innerPid -> assertThat(innerPid).isNotEqualTo(outerPid))
                                    .then(insert(inner, "inner"))
                                    .then(independent.boundTenant().defaultIfEmpty("MISSING")))
                            .contextWrite(Scopes.bind(scope)))
                    .flatMap(innerTenant ->
                        insert(outer, "outer")
                            .then(transactions.boundTenant().defaultIfEmpty("MISSING"))
                            .map(outerTenant -> innerTenant + "/" + outerTenant)))
            .contextWrite(Scopes.bind(scope));

    StepVerifier.create(flow).expectNext("tenant-a/tenant-a").verifyComplete();
    assertThat(notes()).containsExactly("inner", "outer");
  }

  @Test
  void requiresNewWithAnotherScopeIsAnIndependentTransactionAndTheOuterIsRestored() {
    ScopedTransactions independent = new ScopedTransactions(requiresNew(), databaseClient);

    Mono<String> flow =
        transactions
            .inTransaction(outer ->
                independent
                    .inTransaction(inner -> independent.boundTenant().defaultIfEmpty("MISSING"))
                    .contextWrite(Scopes.bind(ScopeContext.of("tenant-b", "person-b")))
                    .flatMap(innerTenant ->
                        transactions
                            .boundTenant()
                            .defaultIfEmpty("MISSING")
                            .map(outerTenant -> innerTenant + "/" + outerTenant)))
            .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")));

    StepVerifier.create(flow).expectNext("tenant-b/tenant-a").verifyComplete();
  }

  @Test
  void sequentialTransactionsInsideASupportsContextBindTheirOwnScope() {
    Mono<String> first = scopedTenant(ScopeContext.of("tenant-a", "person-a"));
    Mono<String> second = scopedTenant(ScopeContext.of("tenant-b", "person-b"));

    StepVerifier.create(
            supportsOperator().transactional(first.flatMap(a -> second.map(b -> a + "/" + b))))
        .expectNext("tenant-a/tenant-b")
        .verifyComplete();
  }

  @Test
  void rollbackCleansUpTheBindingForTheNextTransaction() {
    Mono<String> failing =
        transactions
            .inTransaction(scope ->
                insert(scope, "doomed").then(Mono.<String>error(new IllegalStateException("boom"))))
            .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")))
            .onErrorResume(IllegalStateException.class, error -> Mono.just("rolled-back"));
    Mono<String> next =
        transactions
            .inTransaction(scope -> insert(scope, "next").then(transactions.boundTenant()))
            .contextWrite(Scopes.bind(ScopeContext.of("tenant-b", "person-b")));

    StepVerifier.create(
            supportsOperator().transactional(failing.flatMap(a -> next.map(b -> a + "/" + b))))
        .expectNext("rolled-back/tenant-b")
        .verifyComplete();
    assertThat(notes()).containsExactly("next");
  }

  @Test
  void participationWithoutAnActualTransactionIsRefusedBeforeWork() {
    AtomicBoolean workInvoked = new AtomicBoolean();
    ScopedTransactions unsupported = new ScopedTransactions(supportsOperator(), databaseClient);

    Mono<String> flow =
        unsupported
            .inTransaction(scope -> {
              workInvoked.set(true);
              return insert(scope, "never").thenReturn("never");
            })
            .contextWrite(Scopes.bind(ScopeContext.of("tenant-a", "person-a")));

    StepVerifier.create(flow).expectError(ScopeBindingUnavailableException.class).verify();
    assertThat(workInvoked).isFalse();
    assertThat(notes()).isEmpty();
  }

  @Test
  void sameScopeAcrossDifferentHelperInstancesAndThreadsJoinsTheTransaction() {
    ScopedTransactions otherInstance =
        new ScopedTransactions(transactionalOperator, databaseClient);
    ScopeContext scope = ScopeContext.of("tenant-a", "person-a");

    Mono<String> flow =
        transactions
            .inTransaction(outer ->
                insert(outer, "first")
                    .publishOn(Schedulers.parallel())
                    .then(otherInstance.inTransaction(inner -> otherInstance.boundTenant())))
            .contextWrite(Scopes.bind(scope));

    StepVerifier.create(flow).expectNext("tenant-a").verifyComplete();
    assertThat(notes()).containsExactly("first");
  }

  private Mono<String> scopedTenant(ScopeContext scope) {
    return transactions
        .inTransaction(current -> transactions.boundTenant().defaultIfEmpty("MISSING"))
        .contextWrite(Scopes.bind(scope));
  }

  private TransactionalOperator requiresNew() {
    return operatorWith(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
  }

  private TransactionalOperator supportsOperator() {
    return operatorWith(TransactionDefinition.PROPAGATION_SUPPORTS);
  }

  private TransactionalOperator operatorWith(int propagation) {
    DefaultTransactionDefinition definition = new DefaultTransactionDefinition();
    definition.setPropagationBehavior(propagation);
    return TransactionalOperator.create(transactionManager, definition);
  }

  private Mono<Integer> backendPid() {
    return databaseClient
        .sql("select pg_backend_pid() as pid")
        .map(row -> row.get("pid", Integer.class))
        .one();
  }

  private static Integer assertSameConnection(Integer outerPid, Integer innerPid) {
    assertThat(innerPid).as("nested call joins the outer connection").isEqualTo(outerPid);
    return innerPid;
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
