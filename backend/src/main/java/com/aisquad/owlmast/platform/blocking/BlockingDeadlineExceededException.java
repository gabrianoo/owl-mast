package com.aisquad.owlmast.platform.blocking;

import java.io.Serial;
import java.time.Duration;

/** A blocking call did not finish within its deadline; the caller is released. */
public final class BlockingDeadlineExceededException extends RuntimeException {

  @Serial private static final long serialVersionUID = 1L;

  BlockingDeadlineExceededException(String operation, Duration deadline) {
    super("Blocking operation '%s' exceeded its deadline of %s".formatted(operation, deadline));
  }
}
