package com.aisquad.owlmast.archfixtures.epsilon.api;

import org.springframework.http.HttpStatus;

/** Fixture violation: a published api type that carries a Spring type. */
public record SpringLeakingContract(HttpStatus status) {}
