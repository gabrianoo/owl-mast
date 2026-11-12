package com.aisquad.owlmast.fixtures.restart;

import com.aisquad.owlmast.OwlMastApplication;
import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditActor;
import com.aisquad.owlmast.fixtures.notes.FollowUpHandler;
import com.aisquad.owlmast.fixtures.notes.NotesFixture;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.AuditedMode;
import com.aisquad.owlmast.fixtures.notes.NotesFixture.Failure;
import com.aisquad.owlmast.fixtures.notes.NotesFixtureConfiguration;
import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import com.aisquad.owlmast.testing.StubIdentityConfiguration;
import java.util.Arrays;
import java.util.concurrent.CompletableFuture;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import reactor.core.publisher.Mono;

/**
 * Entry point of a genuinely separate application process for {@code ProcessRestartRecoveryIT}
 * (AC6). It runs the real {@link OwlMastApplication} with the fixture module against the database
 * named on the command line. Two fixture arguments control the scenario:
 *
 * <ul>
 *   <li>{@code --fixture.mode=halt-while-leased}: the follow-up handler, once seeding has finished,
 *       halts the JVM ({@link Runtime#halt}, exit code {@value #HALT_EXIT_CODE}) from inside its
 *       first invocation. The claim committed before the handler ran, so the process dies holding a
 *       live lease it never releases, with no shutdown hook or cleanup, as a SIGKILL would leave
 *       it. Doing this from inside the process removes any timing between an external kill and the
 *       handler deadline.
 *   <li>{@code --fixture.mode=hang-while-leased}: the follow-up handler, once seeding has finished,
 *       never completes, so the process holds a live lease until it is asked to stop (SIGTERM, a
 *       graceful shutdown).
 *   <li>{@code --fixture.seed=true}: after start-up, enqueue work and covered mutations for two
 *       tenants through the published owner APIs.
 * </ul>
 *
 * <p>Everything else is forwarded to Spring as command-line arguments. In every other mode the
 * process stays alive until it is terminated from outside.
 */
public final class RestartFixtureProcess {

  public static final String MODE_HALT_WHILE_LEASED = "--fixture.mode=halt-while-leased";
  public static final String MODE_HANG_WHILE_LEASED = "--fixture.mode=hang-while-leased";
  public static final String SEED = "--fixture.seed=true";
  public static final int HALT_EXIT_CODE = 137;
  public static final int SEEDED_FOLLOW_UPS = 4;
  public static final int SEEDED_MUTATIONS = 3;

  private static final ScopeContext TENANT_A = ScopeContext.of("tenant-a", "person-a");
  private static final ScopeContext TENANT_B = ScopeContext.of("tenant-b", "person-b");

  private RestartFixtureProcess() {}

  public static void main(String[] args) throws InterruptedException {
    boolean halt = Arrays.asList(args).contains(MODE_HALT_WHILE_LEASED);
    boolean hang = Arrays.asList(args).contains(MODE_HANG_WHILE_LEASED);
    boolean seed = Arrays.asList(args).contains(SEED);
    String[] springArgs =
        Arrays.stream(args).filter(arg -> !arg.startsWith("--fixture.")).toArray(String[]::new);

    ConfigurableApplicationContext context =
        new SpringApplicationBuilder(
                OwlMastApplication.class,
                StubIdentityConfiguration.class,
                NotesFixtureConfiguration.class)
            .run(springArgs);
    CompletableFuture<Void> seeded = new CompletableFuture<>();
    if (halt) {
      // Waits (without blocking a thread) until every seeded row exists, then dies mid-attempt.
      context
          .getBean(FollowUpHandler.class)
          .behave(item ->
              Mono.fromFuture(seeded)
                  .then(Mono.fromRunnable(() -> Runtime.getRuntime().halt(HALT_EXIT_CODE))));
    }
    if (hang) {
      context
          .getBean(FollowUpHandler.class)
          .behave(item -> Mono.fromFuture(seeded).then(Mono.never()));
    }
    if (seed) {
      seed(context.getBean(NotesFixture.class));
    }
    seeded.complete(null);
    System.out.println("OWLMAST-FIXTURE-READY");
    Thread.currentThread().join();
  }

  private static void seed(NotesFixture notes) {
    notes.ensureTable().block();
    AuditActor actor = AuditActor.of(ActorKind.HUMAN, "person-a");
    for (int i = 0; i < 3; i++) {
      notes.createWithFollowUp("a-" + i, Failure.NONE).contextWrite(Scopes.bind(TENANT_A)).block();
    }
    notes.createWithFollowUp("b-0", Failure.NONE).contextWrite(Scopes.bind(TENANT_B)).block();
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
