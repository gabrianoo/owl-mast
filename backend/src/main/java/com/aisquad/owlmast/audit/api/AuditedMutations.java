package com.aisquad.owlmast.audit.api;

import reactor.core.publisher.Mono;

/**
 * Owner API through which features perform covered mutations (AD-6, AC3). Requires a bound {@code
 * ScopeContext}. On success the business change, a {@code SUCCEEDED} audit-publication intent and
 * the {@code audit.publish} work item commit in one transaction. On failure the business
 * transaction rolls back and a {@code FAILED} record (or {@code DENIED} for an {@code
 * OperationDeniedException}) is written in a separate transaction before the error is re-signalled;
 * a cancellation or an enclosing rollback is recorded the same way, and an unknown commit outcome
 * as {@code UNRESOLVED}. Exactly one such record exists for the execution whenever one of those
 * separate writes commits; if every one of them fails (for example, the database is unreachable)
 * only a safe log line remains. The error's message is never persisted or logged, only its
 * exception class chain.
 */
public interface AuditedMutations {

  <T> Mono<AuditedResult<T>> execute(AuditedMutation<T> mutation);
}
