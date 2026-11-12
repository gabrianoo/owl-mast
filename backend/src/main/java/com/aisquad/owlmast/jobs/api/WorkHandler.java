package com.aisquad.owlmast.jobs.api;

import reactor.core.publisher.Mono;

/**
 * A feature's processor for one {@link WorkType}, registered as a Spring bean. It is invoked inside
 * a scoped transaction bound to the item's tenant under the backend service identity; database
 * writes it makes commit together with the item's completion and roll back when the lease turned
 * out to be stale. External effects must be deduplicated with {@link WorkItem#idempotencyKey()} or
 * reported as {@link EffectOutcome#uncertain(String)}. An error signal counts as a failed attempt;
 * its message is never persisted, only its exception class chain.
 */
public interface WorkHandler {

  WorkRegistration registration();

  Mono<EffectOutcome> handle(WorkItem item);
}
