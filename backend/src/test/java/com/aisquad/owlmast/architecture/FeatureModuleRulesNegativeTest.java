package com.aisquad.owlmast.architecture;

import static org.assertj.core.api.Assertions.assertThat;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

/** The rules must reject each deliberate violation with a diagnostic naming it (AC2). */
class FeatureModuleRulesNegativeTest {

  private static final String ROOT = "com.aisquad.owlmast.archfixtures";

  @Test
  void deliberateViolationsAreReportedWithUsefulDiagnostics() {
    JavaClasses fixtures = new ClassFileImporter().importPackages(ROOT);

    Map<String, List<String>> violationsByRule =
        FeatureModuleRules.forRoot(ROOT).evaluateAll(fixtures).entrySet().stream()
            .filter(entry -> entry.getValue().hasViolation())
            .collect(
                Collectors.toMap(
                    Map.Entry::getKey, entry -> entry.getValue().getFailureReport().getDetails()));

    assertThat(violationsByRule)
        .hasEntrySatisfying(
            "platform must not depend on feature packages",
            lines ->
                assertThat(lines)
                    .anyMatch(l -> l.contains("LeakyPlatform") && l.contains("AlphaService")))
        .hasEntrySatisfying(
            "only 'alpha.api' may be used outside feature 'alpha'",
            lines ->
                assertThat(lines)
                    .anyMatch(l -> l.contains("BetaService") && l.contains("AlphaRepository"))
                    .noneMatch(l -> l.contains("AlphaView")))
        .hasEntrySatisfying(
            "api/application/domain must not block on publishers",
            lines ->
                assertThat(lines)
                    .anyMatch(l -> l.contains("BlockingService") && l.contains("block()")))
        .hasEntrySatisfying(
            "ThreadLocal must not carry authorization or tenant state (AD-5)",
            lines -> assertThat(lines).anyMatch(l -> l.contains("ThreadLocalAuthorization")))
        .hasEntrySatisfying(
            "application/port must not depend on adapters",
            lines -> assertThat(lines).anyMatch(l -> l.contains("BetaService")));
    assertThat(violationsByRule)
        .doesNotContainKey("only 'beta.api' may be used outside feature 'beta'");
  }
}
