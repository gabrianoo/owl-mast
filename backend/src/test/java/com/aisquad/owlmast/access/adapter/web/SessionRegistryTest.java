package com.aisquad.owlmast.access.adapter.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.access.adapter.web.SessionRegistry.Entry;
import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import java.time.Duration;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.WebSession;
import org.springframework.web.server.session.InMemoryWebSessionStore;

class SessionRegistryTest {

  private static final String ISSUER = "https://id.example/realms/owl-mast";

  private final InMemoryWebSessionStore store = new InMemoryWebSessionStore();
  private final SessionRegistry registry = new SessionRegistry();

  @Test
  void aNoticeNamingASessionCoversThatSessionOnly() {
    register("ref-1", "ada", "sid-1");
    register("ref-2", "ada", "sid-2");
    register("ref-3", "grace", "sid-3");

    assertThat(registry.matching(new ExternalIdentity(ISSUER, "ada"), Optional.of("sid-2")))
        .extracting(Entry::sessionRef)
        .containsExactly("ref-2");
    // The session id decides, not the subject the notice happens to carry.
    assertThat(registry.matching(new ExternalIdentity(ISSUER, "-"), Optional.of("sid-3")))
        .extracting(Entry::sessionRef)
        .containsExactly("ref-3");
    assertThat(registry.matching(new ExternalIdentity(ISSUER, "ada"), Optional.of("unknown")))
        .isEmpty();
  }

  @Test
  void aNoticeNamingNoSessionCoversEverySessionOfThePerson() {
    register("ref-1", "ada", "sid-1");
    register("ref-2", "ada", null);
    register("ref-3", "grace", "sid-3");

    assertThat(registry.matching(new ExternalIdentity(ISSUER, "ada"), Optional.empty()))
        .extracting(Entry::sessionRef)
        .containsExactlyInAnyOrder("ref-1", "ref-2");
  }

  @Test
  void aNoticeOfAnotherIssuerCoversNothing() {
    register("ref-1", "ada", "sid-1");

    assertThat(
            registry.matching(
                new ExternalIdentity("https://id.example/realms/other", "ada"),
                Optional.of("sid-1")))
        .isEmpty();
    assertThat(
            registry.matching(
                new ExternalIdentity("https://id.example/realms/other", "ada"), Optional.empty()))
        .isEmpty();
  }

  @Test
  void anEarlierSignInInTheSameBrowserSessionIsFoundByItsSession() {
    Entry first = register("ref-1", "ada", "sid-1");
    register("ref-2", "grace", "sid-2");
    Entry second =
        new Entry(
            first.session(),
            new PrincipalId("person:ref-3"),
            "ref-3",
            new ExternalIdentity(ISSUER, "ada"),
            Optional.of("sid-3"));

    assertThat(registry.heldBy(first.session()))
        .extracting(Entry::sessionRef)
        .containsExactly("ref-1");
    registry.register(second);
    assertThat(registry.heldBy(first.session()))
        .extracting(Entry::sessionRef)
        .containsExactlyInAnyOrder("ref-1", "ref-3");
  }

  @Test
  void anEndIsTakenOnce() {
    register("ref-1", "ada", "sid-1");

    assertThat(registry.remove("ref-1")).isPresent();
    assertThat(registry.remove("ref-1")).isEmpty();
    assertThat(registry.size()).isZero();
  }

  @Test
  void aSessionTheStoreDroppedIsReportedAsExpired() {
    Entry live = register("ref-1", "ada", "sid-1");
    Entry idle = register("ref-2", "grace", "sid-2");
    idle.session().setMaxIdleTime(Duration.ofNanos(1));

    assertThat(live.session().isExpired()).isFalse();
    assertThat(registry.expired()).extracting(Entry::sessionRef).containsExactly("ref-2");
  }

  private Entry register(String sessionRef, String subject, String providerSessionId) {
    WebSession session = store.createWebSession().block(Duration.ofSeconds(5));
    session.start();
    Entry entry =
        new Entry(
            session,
            new PrincipalId("person:" + sessionRef),
            sessionRef,
            new ExternalIdentity(ISSUER, subject),
            Optional.ofNullable(providerSessionId));
    registry.register(entry);
    return entry;
  }
}
