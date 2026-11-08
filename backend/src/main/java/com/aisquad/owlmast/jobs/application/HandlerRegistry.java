package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkType;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** Handlers by work type; exactly one handler per type, decided at startup. */
public final class HandlerRegistry {

  private final Map<WorkType, WorkHandler> handlers;

  public HandlerRegistry(Collection<? extends WorkHandler> registered) {
    Map<WorkType, WorkHandler> byType = new LinkedHashMap<>();
    for (WorkHandler handler : registered) {
      WorkType type = handler.registration().type();
      WorkHandler previous = byType.putIfAbsent(type, handler);
      if (previous != null) {
        throw new IllegalStateException(
            "Two work handlers register the type '"
                + type.value()
                + "': "
                + previous.getClass().getName()
                + " and "
                + handler.getClass().getName());
      }
    }
    this.handlers = Map.copyOf(byType);
  }

  public Optional<WorkHandler> find(WorkType type) {
    return Optional.ofNullable(handlers.get(type));
  }

  public Set<WorkType> types() {
    return handlers.keySet();
  }
}
