package com.aisquad.owlmast.access.adapter.persistence;

import com.aisquad.owlmast.access.domain.ExternalIdentity;
import com.aisquad.owlmast.access.port.PrincipalStore;
import com.aisquad.owlmast.platform.scope.PrincipalId;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

/**
 * {@code access.principal} over R2DBC. Every statement takes the tenant from the transaction-local
 * setting {@code owlmast.tenant_id} that {@code ScopedTransactions} bound, like the jobs and audit
 * tables; outside a scoped transaction the setting is absent and the statements fail.
 */
@RequiredArgsConstructor
public final class R2dbcPrincipalStore implements PrincipalStore {

  /** Prefix of a person's principal id; the backend's own identity uses {@code service:}. */
  static final String PERSON_PREFIX = "person:";

  private final DatabaseClient client;

  @Override
  public Mono<PrincipalId> bind(ExternalIdentity identity) {
    // Read first: a principal exists for all but a person's first credential, and a bearer call
    // binds on every request, so the common case must not write.
    return client
        .sql(
            """
            SELECT principal_id FROM access.principal
             WHERE tenant_id = current_setting('owlmast.tenant_id')
               AND issuer = :issuer AND subject = :subject
            """)
        .bind("issuer", identity.issuer())
        .bind("subject", identity.subject())
        .map(row -> row.get("principal_id", UUID.class))
        .one()
        .switchIfEmpty(Mono.defer(() -> create(identity)))
        .map(id -> new PrincipalId(PERSON_PREFIX + id));
  }

  private Mono<UUID> create(ExternalIdentity identity) {
    // The no-op update makes the statement return the existing row's id as well: two first
    // sign-ins of one person that race agree on one principal.
    return client
        .sql(
            """
            INSERT INTO access.principal (principal_id, tenant_id, issuer, subject)
            VALUES (:id, current_setting('owlmast.tenant_id'), :issuer, :subject)
            ON CONFLICT ON CONSTRAINT principal_identity_key
            DO UPDATE SET issuer = EXCLUDED.issuer
            RETURNING principal_id
            """)
        .bind("id", UUID.randomUUID())
        .bind("issuer", identity.issuer())
        .bind("subject", identity.subject())
        .map(row -> row.get("principal_id", UUID.class))
        .one();
  }

  @Override
  public Mono<Long> recordSignIn(PrincipalId principal) {
    return Mono.justOrEmpty(uuidOf(principal))
        .flatMap(id ->
            client
                .sql(
                    """
                    UPDATE access.principal
                       SET last_sign_in_at = now(), sign_in_count = sign_in_count + 1
                     WHERE principal_id = :id
                       AND tenant_id = current_setting('owlmast.tenant_id')
                    RETURNING sign_in_count
                    """)
                .bind("id", id)
                .map(row -> row.get("sign_in_count", Long.class))
                .one());
  }

  private static Optional<UUID> uuidOf(PrincipalId principal) {
    String value = principal.value();
    if (!value.startsWith(PERSON_PREFIX)) {
      return Optional.empty();
    }
    try {
      return Optional.of(UUID.fromString(value.substring(PERSON_PREFIX.length())));
    } catch (IllegalArgumentException malformed) {
      return Optional.empty();
    }
  }
}
