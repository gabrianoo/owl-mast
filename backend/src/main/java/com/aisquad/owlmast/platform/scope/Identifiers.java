package com.aisquad.owlmast.platform.scope;

final class Identifiers {

  private Identifiers() {}

  static void requireIdentifier(String value, String name) {
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(name + " must not be blank");
    }
  }
}
