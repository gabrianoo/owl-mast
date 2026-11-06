package com.aisquad.owlmast.platform.blocking;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aisquad.owlmast.platform.scope.ScopeContext;
import com.aisquad.owlmast.platform.scope.Scopes;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class BoundedBlockingTest {

  private final BoundedBlocking blocking =
      BoundedBlocking.create(new BoundedBlockingProperties(1, 1, Duration.ofSeconds(5)));

  @AfterEach
  void close() {
    blocking.close();
  }

  @Test
  void runsBlockingWorkOffTheCallingThreadAndKeepsTheReactorContext() {
    ScopeContext scope = ScopeContext.of("aisquad", "person-1");
    String callerThread = Thread.currentThread().getName();

    Mono<String> flow =
        Scopes.current()
            .flatMap(current ->
                blocking.call(
                    "legacy-sdk",
                    () -> current.tenant().value() + "@" + Thread.currentThread().getName()))
            .flatMap(
                result -> Scopes.current().map(after -> result + "|" + after.principal().value()))
            .contextWrite(Scopes.bind(scope));

    StepVerifier.create(flow)
        .assertNext(value ->
            assertThat(value)
                .startsWith("aisquad@owlmast-blocking")
                .doesNotContain(callerThread)
                .endsWith("|person-1"))
        .verifyComplete();
  }

  @Test
  void deadlineReleasesTheCallerWithATypedError() {
    Mono<String> slow =
        blocking.call(
            "slow-sdk",
            Duration.ofMillis(100),
            () -> {
              Thread.sleep(5_000);
              return "late";
            });

    StepVerifier.create(slow)
        .expectErrorSatisfies(error ->
            assertThat(error)
                .isInstanceOf(BlockingDeadlineExceededException.class)
                .hasMessageContaining("slow-sdk")
                .hasMessageContaining("PT0.1S"))
        .verify(Duration.ofSeconds(5));
  }

  @Test
  void capacityBeyondThreadsAndQueueIsRejectedExplicitly() throws InterruptedException {
    CountDownLatch release = new CountDownLatch(1);
    CountDownLatch occupied = new CountDownLatch(1);
    Mono<String> occupying =
        blocking.call(
            "occupying",
            () -> {
              occupied.countDown();
              release.await(5, TimeUnit.SECONDS);
              return "done";
            });
    var first = occupying.subscribe();
    assertThat(occupied.await(5, TimeUnit.SECONDS)).isTrue();
    // One thread is busy and one call is queued; the next call must be rejected, not queued.
    var queued = blocking.call("queued", () -> "queued").subscribe();

    Mono<String> rejected = blocking.call("overflow", () -> "never");

    StepVerifier.create(rejected)
        .expectErrorSatisfies(error ->
            assertThat(error)
                .isInstanceOf(BlockingCapacityExceededException.class)
                .hasMessageContaining("overflow")
                .hasMessageContaining("1 concurrent threads and 1 queued"))
        .verify(Duration.ofSeconds(5));
    release.countDown();
    queued.dispose();
    first.dispose();
  }

  @Test
  void propertiesRejectUnboundedConfiguration() {
    assertThatThrownBy(() -> new BoundedBlockingProperties(0, 1, Duration.ofSeconds(1)))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("max-concurrency");
    assertThatThrownBy(() -> new BoundedBlockingProperties(1, 0, Duration.ofSeconds(1)))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("max-queued-per-thread");
    assertThatThrownBy(() -> new BoundedBlockingProperties(1, 1, Duration.ZERO))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("deadline");
  }
}
