package com.aisquad.owlmast.jobs.api;

import java.util.UUID;
import reactor.core.publisher.Mono;

/**
 * Owner API through which features enqueue durable work (AD-6). The call requires a bound {@code
 * ScopeContext} and joins the caller's scoped transaction when one is active, so a business row and
 * its work record commit or roll back together (AC1); outside a transaction it opens one. It fails
 * closed without a scope or with a scope different from the active transaction's.
 */
public interface WorkEnqueue {

  /** Returns the new item's id once the insert has been issued inside the transaction. */
  Mono<UUID> enqueue(EnqueueRequest request);
}
