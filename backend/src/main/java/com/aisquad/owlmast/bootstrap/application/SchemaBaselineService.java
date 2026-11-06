package com.aisquad.owlmast.bootstrap.application;

import com.aisquad.owlmast.bootstrap.api.SchemaBaseline;
import com.aisquad.owlmast.bootstrap.api.SchemaBaselineQuery;
import com.aisquad.owlmast.bootstrap.port.SchemaBaselineRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
@RequiredArgsConstructor
class SchemaBaselineService implements SchemaBaselineQuery {

  private final SchemaBaselineRepository repository;

  @Override
  public Mono<SchemaBaseline> current() {
    return repository.findBaseline();
  }
}
