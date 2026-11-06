package com.aisquad.owlmast.platform.scope;

/** Trusted tenant identity derived from validated identity, never from a payload claim (AD-4). */
public record TenantId(String value) {

  public TenantId {
    Identifiers.requireIdentifier(value, "tenant id");
  }
}
