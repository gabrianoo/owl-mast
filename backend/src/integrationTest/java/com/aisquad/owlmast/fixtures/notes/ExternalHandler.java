package com.aisquad.owlmast.fixtures.notes;

import com.aisquad.owlmast.jobs.api.EffectOutcome;
import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import com.aisquad.owlmast.jobs.api.WorkType;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

/**
 * Fixture handler that is <em>not</em> tenant-internal system work: until OM-02.04 the default
 * dispatch recheck must deny it without ever invoking it (AC7).
 */
public final class ExternalHandler implements WorkHandler {

  public static final WorkType TYPE = WorkType.of("fixture.external");

  private final AtomicInteger invocations = new AtomicInteger();

  @Override
  public WorkRegistration registration() {
    return WorkRegistration.requiresAuthorization(TYPE);
  }

  @Override
  public Mono<EffectOutcome> handle(WorkItem item) {
    invocations.incrementAndGet();
    return Mono.just(EffectOutcome.applied(item.idempotencyKey()));
  }

  public int invocations() {
    return invocations.get();
  }
}
