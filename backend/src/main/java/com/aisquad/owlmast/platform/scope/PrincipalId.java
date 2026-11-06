package com.aisquad.owlmast.platform.scope;

/** Identity of the person or enrolled client acting in a request or job (AD-3). */
public record PrincipalId(String value) {

  public PrincipalId {
    Identifiers.requireIdentifier(value, "principal id");
  }
}
