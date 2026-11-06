package com.aisquad.owlmast.archfixtures.delta.application;

/** Fixture violation: ThreadLocal-only authorization state. */
public final class ThreadLocalAuthorization {

  private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

  public static void bind(String tenant) {
    TENANT.set(tenant);
  }

  public static String current() {
    return TENANT.get();
  }
}
