package com.aisquad.owlmast.platform.diagnostics;

import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;
import lombok.AccessLevel;
import lombok.NoArgsConstructor;

/**
 * Bounded, secret-free description of a failure for logs and diagnostics (NFR-6). Only exception
 * class names of the cause chain are reported; messages, stack traces and suppressed exceptions are
 * never included because drivers and SDKs put connection strings, credentials and payload fragments
 * into them.
 */
@NoArgsConstructor(access = AccessLevel.PRIVATE)
public final class SafeFailure {

  static final int MAX_DEPTH = 5;

  /** For example {@code IllegalStateException <- PSQLException}. */
  public static String describe(Throwable failure) {
    if (failure == null) {
      return "unknown failure";
    }
    List<String> chain = new ArrayList<>();
    Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<>());
    Throwable current = failure;
    while (current != null && chain.size() < MAX_DEPTH && seen.add(current)) {
      chain.add(current.getClass().getSimpleName());
      current = current.getCause();
    }
    if (current != null && !seen.contains(current)) {
      chain.add("…");
    }
    return String.join(" <- ", chain);
  }
}
