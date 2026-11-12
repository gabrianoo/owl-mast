package com.aisquad.owlmast.jobs.api;

import reactor.core.publisher.Flux;

/**
 * Operator listing of terminal failures (AC5). Requires a bound {@code ScopeContext}: only the
 * bound tenant's items are returned, newest first, never their payloads. Authorization of the
 * operator beyond tenant scope arrives with E02; until then the scope binding is the gate.
 */
public interface FailedWorkQuery {

  Flux<FailedWorkItem> listTerminalFailures(int limit);
}
