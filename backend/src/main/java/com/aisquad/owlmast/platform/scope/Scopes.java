package com.aisquad.owlmast.platform.scope;

import java.util.Optional;
import java.util.function.Function;
import lombok.AccessLevel;
import lombok.NoArgsConstructor;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;
import reactor.util.context.ContextView;

/** Reads and binds the {@link ScopeContext} in the Reactor Context. There is no default scope. */
@NoArgsConstructor(access = AccessLevel.PRIVATE)
public final class Scopes {

  private static final Class<ScopeContext> KEY = ScopeContext.class;

  /** The current scope, or a {@link MissingScopeException} when none is bound. */
  public static Mono<ScopeContext> current() {
    return Mono.deferContextual(
        view -> peek(view).map(Mono::just).orElseGet(() -> Mono.error(MissingScopeException::new)));
  }

  /** Context mutation for {@code contextWrite(Scopes.bind(scope))}. */
  public static Function<Context, Context> bind(ScopeContext scope) {
    return context -> context.put(KEY, scope);
  }

  public static Optional<ScopeContext> peek(ContextView view) {
    return view.getOrEmpty(KEY);
  }
}
