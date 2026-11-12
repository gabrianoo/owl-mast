package com.aisquad.owlmast.jobs.api;

import reactor.core.publisher.Mono;

/**
 * Authorization recheck port consulted before every handler dispatch (AD-4, AD-6). The access
 * module supplies the real implementation in OM-02.04 as a Spring bean of this type; until then the
 * jobs owner falls back to a default that allows only handlers registered as tenant-internal system
 * work and denies all others. An error signal is treated as {@link DispatchDecision#UNDECIDED}: the
 * handler is not invoked.
 */
public interface DispatchAuthorization {

  Mono<DispatchDecision> recheck(WorkItem item, WorkRegistration registration);
}
