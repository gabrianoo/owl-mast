package com.aisquad.owlmast.bootstrap.adapter.persistence;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import com.aisquad.owlmast.bootstrap.port.SchemaBaselineRepository;
import java.time.OffsetDateTime;
import lombok.RequiredArgsConstructor;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
@RequiredArgsConstructor
class R2dbcSchemaBaselineRepository implements SchemaBaselineRepository {

  private final DatabaseClient databaseClient;

  @Override
  public Mono<SchemaBaseline> findBaseline() {
    return databaseClient
        .sql(
            "select vchord_version, vector_version, applied_at,"
                + " cast(current_setting('server_version_num') as integer) as server_version_num"
                + " from bootstrap.schema_baseline where id = 1")
        .map(row ->
            new SchemaBaseline(
                row.get("vchord_version", String.class),
                row.get("vector_version", String.class),
                row.get("applied_at", OffsetDateTime.class).toInstant(),
                row.get("server_version_num", Integer.class)))
        .one();
  }
}
