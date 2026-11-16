package com.aisquad.owlmast.access.adapter.web;

import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.web.server.WebSession;

/**
 * Who holds which signed-in session, kept next to the in-memory session store. It exists for two
 * things the store cannot do: finding the sessions the identity provider announces as ended (by its
 * session id or by the person), and noticing that the store dropped a session, so that the end is
 * recorded. An entry is removed by whoever ends the session, before it is ended, which is what
 * keeps one end from being recorded twice.
 *
 * <p>Entries are keyed by the session's reference, not by its id: the id is the browser's
 * credential and is replaced when a session is authenticated, while the reference is fixed at
 * sign-in. The entry holds the session object itself, which stays the same across an id change.
 */
final class SessionRegistry {

  /** A signed-in session and what is known about it without its credential. */
  record Entry(
      WebSession session,
      PrincipalId principal,
      String sessionRef,
      ExternalIdentity identity,
      Optional<String> providerSessionId) {

    static Entry of(WebSession session, SignedInPerson person) {
      return new Entry(
          session,
          person.principalId(),
          person.sessionRef(),
          person.identity(),
          person.providerSessionId());
    }
  }

  private final ConcurrentHashMap<String, Entry> bySessionRef = new ConcurrentHashMap<>();

  void register(Entry entry) {
    bySessionRef.put(entry.sessionRef(), entry);
  }

  /** Removes and returns the entry; empty when another path already ended the session. */
  Optional<Entry> remove(String sessionRef) {
    return Optional.ofNullable(bySessionRef.remove(sessionRef));
  }

  /**
   * The sessions the identity provider's notice covers: the one session it names, or, when it names
   * none, every session of the person.
   */
  List<Entry> matching(ExternalIdentity identity, Optional<String> providerSessionId) {
    return bySessionRef.values().stream()
        .filter(entry -> entry.identity().issuer().equals(identity.issuer()))
        .filter(entry ->
            providerSessionId
                .map(sid -> entry.providerSessionId().filter(sid::equals).isPresent())
                .orElseGet(() -> entry.identity().subject().equals(identity.subject())))
        .toList();
  }

  /**
   * The entries registered for this very session object (a session is equal only to itself):
   * earlier sign-ins in the same browser session.
   */
  List<Entry> heldBy(WebSession session) {
    return bySessionRef.values().stream().filter(entry -> entry.session().equals(session)).toList();
  }

  /** The registered sessions that have expired in the store. */
  List<Entry> expired() {
    return bySessionRef.values().stream().filter(entry -> entry.session().isExpired()).toList();
  }

  int size() {
    return bySessionRef.size();
  }
}
