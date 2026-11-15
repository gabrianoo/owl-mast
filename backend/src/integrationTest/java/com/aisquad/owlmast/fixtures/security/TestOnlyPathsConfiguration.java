package com.aisquad.owlmast.fixtures.security;

import com.aisquad.owlmast.platform.web.ProblemResponses;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

/**
 * Opens {@code /api/test-only/**} to callers without a credential, for tests whose subject is not
 * authentication (the error envelope). It exists only in the integration-test source set: the
 * production chain has no setting that opens a path, and every other path stays behind it.
 *
 * <p>The chain answers a denial the way the production chain does (401 with the challenge for a
 * caller nobody authenticated, 403 otherwise, both in the problem-details envelope), so a test that
 * raises a security exception from a test-only controller still reads the envelope. The production
 * chain's own answers are proven by the sign-in tests.
 */
@TestConfiguration(proxyBeanMethods = false)
public class TestOnlyPathsConfiguration {

  public static final String PATTERN = "/api/test-only/**";

  @Bean
  @Order(Ordered.HIGHEST_PRECEDENCE)
  SecurityWebFilterChain testOnlyPaths(ServerHttpSecurity http, ProblemResponses problems) {
    return http.securityMatcher(new PathPatternParserServerWebExchangeMatcher(PATTERN))
        .authorizeExchange(exchanges -> exchanges.anyExchange().permitAll())
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .exceptionHandling(handling ->
            handling
                .authenticationEntryPoint((exchange, failure) ->
                    problems.write(
                        exchange,
                        HttpStatus.UNAUTHORIZED,
                        headers -> headers.set(HttpHeaders.WWW_AUTHENTICATE, "Bearer")))
                .accessDeniedHandler(
                    (exchange, failure) -> problems.write(exchange, HttpStatus.FORBIDDEN)))
        .build();
  }
}
