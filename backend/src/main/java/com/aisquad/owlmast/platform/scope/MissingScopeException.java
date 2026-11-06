package com.aisquad.owlmast.platform.scope;

/**
 * Raised when an operation requires a {@link ScopeContext} and none was established: fail closed.
 */
public final class MissingScopeException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  public MissingScopeException() {
    super(
        "No ScopeContext present in the Reactor Context; tenant/security scope must be bound"
            + " explicitly with Scopes.bind(...) before this operation runs (AD-4, AD-5)");
  }
}
