package com.aisquad.owlmast.platform.blocking;

/** The bounded blocking adapter refused a call because its thread and queue capacity is full. */
public final class BlockingCapacityExceededException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  BlockingCapacityExceededException(String operation, int maxConcurrency, int maxQueuedPerThread) {
    super(
        ("Blocking operation '%s' rejected: capacity of %d concurrent threads and %d queued calls"
                + " per thread exhausted")
            .formatted(operation, maxConcurrency, maxQueuedPerThread));
  }
}
