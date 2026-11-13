package com.aisquad.owlmast.jobs.application;

import com.aisquad.owlmast.jobs.api.WorkHandler;
import com.aisquad.owlmast.jobs.api.WorkRegistration;
import com.aisquad.owlmast.jobs.api.WorkType;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * Handlers by work type; exactly one handler per type, decided at startup. Each handler's
 * registration is read once, here: a handler that asks for the tenant-internal system-work
 * privilege for a type the jobs owner has not granted ({@link TenantInternalGrants}) is refused, so
 * the application does not start with a self-granted privilege. The registration read at startup is
 * the one every later dispatch and enqueue uses, whatever the handler answers afterwards.
 */
public final class HandlerRegistry {

  private final Map<WorkType, Registered> handlers;

  public HandlerRegistry(
      Collection<? extends WorkHandler> registered, TenantInternalGrants grants) {
    Objects.requireNonNull(grants, "grants");
    Map<WorkType, Registered> byType = new LinkedHashMap<>();
    for (WorkHandler handler : registered) {
      WorkRegistration registration =
          Objects.requireNonNull(handler.registration(), "registration");
      WorkType type = registration.type();
      if (registration.tenantInternalSystemWork() && !grants.contains(type)) {
        throw new IllegalStateException(
            "Work handler "
                + handler.getClass().getName()
                + " registers the type '"
                + type.value()
                + "' as tenant-internal system work, but the jobs owner has not granted that type"
                + " the privilege (TenantInternalGrants); a feature module cannot grant it to"
                + " itself");
      }
      Registered previous = byType.putIfAbsent(type, new Registered(handler, registration));
      if (previous != null) {
        throw new IllegalStateException(
            "Two work handlers register the type '"
                + type.value()
                + "': "
                + previous.handler().getClass().getName()
                + " and "
                + handler.getClass().getName());
      }
    }
    this.handlers = Map.copyOf(byType);
  }

  public Optional<WorkHandler> find(WorkType type) {
    return Optional.ofNullable(handlers.get(type)).map(Registered::handler);
  }

  /** The registration the handler of this type gave at startup. */
  public Optional<WorkRegistration> registration(WorkType type) {
    return Optional.ofNullable(handlers.get(type)).map(Registered::registration);
  }

  public Set<WorkType> types() {
    return handlers.keySet();
  }

  private record Registered(WorkHandler handler, WorkRegistration registration) {}
}
