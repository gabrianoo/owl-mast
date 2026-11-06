package com.aisquad.owlmast.platform.persistence;

/**
 * {@code ScopedTransactions} was invoked where no actual, synchronized transaction exists (for
 * example an operator configured with {@code PROPAGATION_SUPPORTS} or {@code NEVER} and no outer
 * transaction, or a manager without synchronization). Binding a tenant outside a real transaction
 * would be a session-level or no-op setting, so the call fails before any work (AD-5).
 */
public final class ScopeBindingUnavailableException extends IllegalStateException {

  private static final long serialVersionUID = 1L;

  ScopeBindingUnavailableException() {
    super(
        "ScopedTransactions requires an actual transaction with synchronization active; the"
            + " configured TransactionalOperator did not provide one, so the tenant scope cannot be"
            + " bound to a transaction and the work is refused");
  }
}
