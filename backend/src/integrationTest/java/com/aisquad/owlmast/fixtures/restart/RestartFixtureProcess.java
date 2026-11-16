package com.aisquad.owlmast.fixtures.restart;

import com.aisquad.owlmast.OwlMastApplication;
import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.fixtures.notes.FollowUpHandler;
import com.aisquad.owlmast.fixtures.notes.NotesFixture;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.AuditedMode;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.Failure;
import com.aisquad.owlmast.fixtures.notes.NotesFixtureConfiguration;
import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Function;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

/**
 * Entry point of a genuinely separate application process for {@code ProcessRestartRecoveryIT}
 * (AC6) and {@code OverlappingBackendsIT}. It runs the real {@link OwlMastApplication} with the
 * fixture module against the database named on the command line. The fixture arguments control the
 * scenario:
 *
 * <ul>
 *   <li>{@code --fixture.mode=normal} (also when no mode is given): the follow-up handler applies
 *       its effect. Any other value than the modes listed here is refused.
 *   <li>{@code --fixture.mode=halt-while-leased}: the follow-up handler, once seeding has finished,
 *       halts the JVM ({@link Runtime#halt}, exit code {@value #HALT_EXIT_CODE}) from inside its
 *       first invocation. The claim committed before the handler ran, so the process dies holding a
 *       live lease it never releases, with no shutdown hook or cleanup, as a SIGKILL would leave
 *       it. Doing this from inside the process removes any timing between an external kill and the
 *       handler deadline.
 *   <li>{@code --fixture.mode=hang-while-leased}: the follow-up handler, once seeding has finished,
 *       never completes, so the process holds a live lease until it is asked to stop (SIGTERM, a
 *       graceful shutdown).
 *   <li>{@code --fixture.mode=slow}: every follow-up takes {@link #SLOW_HANDLER} before it applies
 *       its effect, so one process cannot drain a queue before another one takes part.
 *   <li>{@code --fixture.mode=finish-after-reclaimed}: the first follow-up this process is handed
 *       waits until another process has completed that same item, and only then applies its effect
 *       and returns, so its completion write arrives under a lease that was lost.
 *   <li>{@code --fixture.mode=effect-then-wait}: commit the external effect, then wait without
 *       completing the work row, for interruption tests.
 *   <li>{@code --fixture.mode=statement-wait}: insert in the handler transaction, then wait in a
 *       database statement, for rollback-on-shutdown tests.
 *   <li>{@code --fixture.deduplicate=true}: additionally deliver to a durable unique-key receiver;
 *       the raw effect log still counts every delivery. Use with {@code --fixture.effect-log=true}.
 *   <li>{@code --fixture.effect-log=true}: the follow-up handler's effect is one row in {@value
 *       #EFFECT_LOG_TABLE} per invocation that reached the effect, written outside the handler's
 *       transaction as an external system would record it, with the instance that wrote it. A
 *       seeding process always creates the table, with or without this argument.
 *   <li>{@code --fixture.seed=true}: after start-up, enqueue work and covered mutations for two
 *       tenants through the published owner APIs. {@code --fixture.extra-follow-ups=<n>} adds
 *       {@code n} more follow-ups, and {@code --fixture.seed-after=<file>} delays the seeding until
 *       that file exists.
 * </ul>
 *
 * <p>Everything else is forwarded to Spring as command-line arguments. The handler has its mode's
 * behaviour before the scheduler's first wake-up. The process prints {@value #STARTED} once the
 * application context is up and {@value #READY} once seeding has finished. In every mode but {@code
 * halt-while-leased} it stays alive until it is terminated from outside.
 */
public final class RestartFixtureProcess {

  public static final String MODE_HALT_WHILE_LEASED = "--fixture.mode=halt-while-leased";
  public static final String MODE_HANG_WHILE_LEASED = "--fixture.mode=hang-while-leased";
  public static final String MODE_NORMAL = "--fixture.mode=normal";
  public static final String MODE_SLOW = "--fixture.mode=slow";
  public static final String MODE_FINISH_AFTER_RECLAIMED = "--fixture.mode=finish-after-reclaimed";
  public static final String MODE_EFFECT_THEN_WAIT = "--fixture.mode=effect-then-wait";
  public static final String MODE_STATEMENT_WAIT = "--fixture.mode=statement-wait";
  public static final String DEDUPLICATE = "--fixture.deduplicate=true";
  public static final String RECEIVER_TABLE = "fixture_receiver_effect";
  public static final String TRANSACTION_TABLE = "fixture_transaction_effect";
  public static final String EFFECT_LOG = "--fixture.effect-log=true";
  public static final String SEED = "--fixture.seed=true";
  public static final String EXTRA_FOLLOW_UPS = "--fixture.extra-follow-ups=";
  public static final String SEED_AFTER = "--fixture.seed-after=";
  public static final String EFFECT_LOG_TABLE = "fixture_effect_log";
  public static final String STARTED = "OWLMAST-FIXTURE-STARTED";
  public static final String READY = "OWLMAST-FIXTURE-READY";
  public static final Duration SLOW_HANDLER = Duration.ofMillis(200);
  public static final int HALT_EXIT_CODE = 137;
  public static final int SEEDED_FOLLOW_UPS = 4;
  public static final int SEEDED_MUTATIONS = 3;

  private static final Set<String> MODES =
      Set.of(
          MODE_NORMAL,
          MODE_HALT_WHILE_LEASED,
          MODE_HANG_WHILE_LEASED,
          MODE_SLOW,
          MODE_FINISH_AFTER_RECLAIMED,
          MODE_EFFECT_THEN_WAIT,
          MODE_STATEMENT_WAIT);

  private static final ScopeContext TENANT_A = ScopeContext.of("tenant-a", "person-a");
  private static final ScopeContext TENANT_B = ScopeContext.of("tenant-b", "person-b");

  private RestartFixtureProcess() {}

  public static void main(String[] args) throws InterruptedException {
    List<String> arguments = Arrays.asList(args);
    List<String> modes =
        arguments.stream().filter(argument -> argument.startsWith("--fixture.mode=")).toList();
    if (modes.size() > 1 || !MODES.containsAll(modes)) {
      throw new IllegalArgumentException("unknown or repeated fixture mode: " + modes);
    }
    String mode = modes.isEmpty() ? MODE_NORMAL : modes.get(0);
    boolean effectLog = arguments.contains(EFFECT_LOG);
    String[] springArgs =
        Arrays.stream(args).filter(arg -> !arg.startsWith("--fixture.")).toArray(String[]::new);
    CompletableFuture<Void> seeded = new CompletableFuture<>();

    // The handler gets its behaviour as soon as its bean exists: the scheduler's first wake-up runs
    // when the context is refreshed, before run() returns, and must not find the default behaviour.
    ConfigurableApplicationContext context =
        new SpringApplicationBuilder(
                OwlMastApplication.class,
                StubIdentityConfiguration.class,
                NotesFixtureConfiguration.class)
            .initializers(starting ->
                starting
                    .getBeanFactory()
                    .addBeanPostProcessor(
                        new BeanPostProcessor() {
                          @Override
                          public Object postProcessAfterInitialization(Object bean, String name) {
                            if (bean instanceof FollowUpHandler handler) {
                              handler.behave(
                                  behaviour(
                                      mode,
                                      effectLog,
                                      arguments.contains(DEDUPLICATE),
                                      handler,
                                      starting,
                                      seeded));
                            }
                            return bean;
                          }
                        }))
            .run(springArgs);
    System.out.println(STARTED);
    if (arguments.contains(SEED)) {
      waitFor(argument(arguments, SEED_AFTER));
      seed(
          context.getBean(NotesFixture.class),
          context.getBean(DatabaseClient.class),
          argument(arguments, EXTRA_FOLLOW_UPS).map(Integer::parseInt).orElse(0));
    }
    seeded.complete(null);
    System.out.println(READY);
    Thread.currentThread().join();
  }

  /**
   * What the follow-up handler does in {@code mode}. The database client and the instance name are
   * read from the context when an item is handled, not when the handler bean is created.
   */
  private static Function<WorkItem, Mono<EffectOutcome>> behaviour(
      String mode,
      boolean effectLog,
      boolean deduplicate,
      FollowUpHandler handler,
      ConfigurableApplicationContext context,
      CompletableFuture<Void> seeded) {
    Function<WorkItem, Mono<EffectOutcome>> effect =
        effectLog
            ? item ->
                recordEffect(
                    context.getBean(DatabaseClient.class),
                    context.getEnvironment().getProperty("owlmast.jobs.instance-id", "unnamed"),
                    item,
                    deduplicate)
            : handler::applyEffect;
    return switch (mode) {
      case MODE_EFFECT_THEN_WAIT ->
          item ->
              Mono.fromFuture(seeded).then(Mono.defer(() -> effect.apply(item))).then(Mono.never());
      case MODE_STATEMENT_WAIT ->
          item ->
              Mono.fromFuture(seeded)
                  .then(
                      context
                          .getBean(DatabaseClient.class)
                          .sql(
                              "insert into "
                                  + TRANSACTION_TABLE
                                  + " (item_id, instance) values (:id, :instance)")
                          .bind("id", item.id())
                          .bind(
                              "instance",
                              context
                                  .getEnvironment()
                                  .getProperty("owlmast.jobs.instance-id", "unnamed"))
                          .then())
                  .then(
                      context
                          .getBean(DatabaseClient.class)
                          .sql("select pg_sleep(120) /* fixture-in-statement */")
                          .then())
                  .then(Mono.defer(() -> effect.apply(item)));

      // Waits (without blocking a thread) until every seeded row exists, then dies mid-attempt.
      case MODE_HALT_WHILE_LEASED ->
          item ->
              Mono.fromFuture(seeded)
                  .then(Mono.fromRunnable(() -> Runtime.getRuntime().halt(HALT_EXIT_CODE)));
      case MODE_HANG_WHILE_LEASED -> item -> Mono.fromFuture(seeded).then(Mono.never());
      case MODE_SLOW -> item -> Mono.delay(SLOW_HANDLER).then(Mono.defer(() -> effect.apply(item)));
      case MODE_FINISH_AFTER_RECLAIMED -> {
        AtomicBoolean first = new AtomicBoolean(true);
        yield item ->
            first.compareAndSet(true, false)
                ? Mono.fromFuture(seeded)
                    .then(
                        Mono.defer(() ->
                            completedByAnotherProcess(
                                context.getBean(DatabaseClient.class),
                                item,
                                context
                                    .getEnvironment()
                                    .getProperty("owlmast.jobs.instance-id", "unnamed"))))
                    .then(Mono.defer(() -> effect.apply(item)))
                : effect.apply(item);
      }
      default -> effect;
    };
  }

  private static Optional<String> argument(List<String> arguments, String prefix) {
    return arguments.stream()
        .filter(argument -> argument.startsWith(prefix))
        .map(argument -> argument.substring(prefix.length()))
        .findFirst();
  }

  private static void waitFor(Optional<String> file) throws InterruptedException {
    if (file.isPresent()) {
      Path signal = Path.of(file.get());
      while (!Files.exists(signal)) {
        Thread.sleep(100);
      }
    }
  }

  /**
   * The external effect of one invocation: a row of its own, on a connection outside the handler's
   * transaction (the empty context drops the transaction), so it stays when the completion write is
   * rejected and the handler's transaction rolls back.
   */
  private static Mono<EffectOutcome> recordEffect(
      DatabaseClient database, String instance, WorkItem item, boolean deduplicate) {
    Mono<Void> delivery =
        database
            .sql(
                "insert into "
                    + EFFECT_LOG_TABLE
                    + " (idempotency_key, item_id, instance, attempt)"
                    + " values (:key, :item, :instance, :attempt)")
            .bind("key", item.idempotencyKey())
            .bind("item", item.id())
            .bind("instance", instance)
            .bind("attempt", item.attempt())
            .then()
            .contextWrite(context -> Context.empty());
    // Receiver owns this unique constraint. Receipt and effect are the same atomic insert here;
    // real receivers must atomically store their receipt with the business effect too.
    Mono<Void> receipt =
        deduplicate
            ? database
                .sql(
                    "insert into "
                        + RECEIVER_TABLE
                        + " (idempotency_key, item_id) values (:key, :item) on conflict (idempotency_key) do nothing")
                .bind("key", item.idempotencyKey())
                .bind("item", item.id())
                .then()
                .contextWrite(context -> Context.empty())
            : Mono.empty();
    return delivery.then(receipt).thenReturn(EffectOutcome.applied(item.idempotencyKey()));
  }

  /** Completes once the item is {@code SUCCEEDED}, which only another process can have written. */
  private static Mono<Void> completedByAnotherProcess(
      DatabaseClient database, WorkItem item, String instance) {
    return database
        .sql(
            "with heartbeat as (insert into fixture_worker_heartbeat(instance, observed_at)"
                + " values (:instance, clock_timestamp()) on conflict(instance) do update"
                + " set observed_at=excluded.observed_at returning 1)"
                + " select 1 from jobs.work_item where id = :id and status = 'SUCCEEDED'")
        .bind("instance", instance)
        .bind("id", item.id())
        .fetch()
        .first()
        .contextWrite(context -> Context.empty())
        .repeatWhenEmpty(
            Integer.MAX_VALUE, attempts -> attempts.delayElements(Duration.ofMillis(100)))
        .then();
  }

  private static void seed(NotesFixture notes, DatabaseClient database, int extraFollowUps) {
    notes.ensureTable().block();
    // Polling opens short-lived connections; this fixture-only heartbeat proves DB activity
    // during a node/API partition without relying on a lucky pg_stat_activity snapshot.
    database
        .sql(
            "create table if not exists fixture_worker_heartbeat"
                + " (instance text primary key, observed_at timestamptz not null)")
        .then()
        .block();
    database
        .sql(
            "create table if not exists "
                + EFFECT_LOG_TABLE
                + " (idempotency_key text not null, item_id uuid not null, instance text not null,"
                + " attempt integer not null,"
                + " recorded_at timestamptz not null default clock_timestamp())")
        .then()
        .block();
    database
        .sql(
            "create table if not exists "
                + RECEIVER_TABLE
                + " (idempotency_key text primary key, item_id uuid not null)")
        .then()
        .block();
    database
        .sql(
            "create table if not exists "
                + TRANSACTION_TABLE
                + " (item_id uuid not null, instance text not null)")
        .then()
        .block();
    AuditActor actor = AuditActor.of(ActorKind.HUMAN, "person-a");
    for (int i = 0; i < 3; i++) {
      notes.createWithFollowUp("a-" + i, Failure.NONE).contextWrite(Scopes.bind(TENANT_A)).block();
    }
    notes.createWithFollowUp("b-0", Failure.NONE).contextWrite(Scopes.bind(TENANT_B)).block();
    for (int i = 0; i < extraFollowUps; i++) {
      ScopeContext tenant = i % 2 == 0 ? TENANT_A : TENANT_B;
      notes
          .createWithFollowUp("extra-" + i, Failure.NONE)
          .contextWrite(Scopes.bind(tenant))
          .block();
    }
    notes
        .auditedCreate("a-audit-1", actor, "corr-r1", AuditedMode.SUCCEED)
        .contextWrite(Scopes.bind(TENANT_A))
        .block();
    notes
        .auditedCreate("a-audit-2", actor, "corr-r2", AuditedMode.SUCCEED)
        .contextWrite(Scopes.bind(TENANT_A))
        .block();
    notes
        .auditedCreate("b-audit-1", actor, "corr-r3", AuditedMode.SUCCEED)
        .contextWrite(Scopes.bind(TENANT_B))
        .block();
  }
}
