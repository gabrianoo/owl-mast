package com.aisquad.owlmast.archfixtures.epsilon.api;

import com.aisquad.owlmast.archfixtures.epsilon.domain.EpsilonRule;

/** Fixture violation: a published api type that exposes the feature's own domain type. */
public record InternalLeakingContract(EpsilonRule rule) {}
