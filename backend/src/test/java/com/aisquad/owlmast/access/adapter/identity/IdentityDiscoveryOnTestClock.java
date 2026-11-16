package com.aisquad.owlmast.access.adapter.identity;

import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.scheduler.Scheduler;

/**
 * The production {@link IdentityDiscovery} with its intervals on a clock a test moves, for tests of
 * other packages: the constructor that takes the timer is not public.
 */
public final class IdentityDiscoveryOnTestClock {

  /** How long a failed read is kept before the provider is asked again. */
  public static final Duration RETRY = IdentityDiscovery.RETRY;

  private IdentityDiscoveryOnTestClock() {}

  public static IdentityDiscovery of(IdentityProperties properties, Scheduler timer) {
    return new IdentityDiscovery(
        WebClient.create(), properties, IdentityDiscovery.KEPT, IdentityDiscovery.RETRY, timer);
  }
}
