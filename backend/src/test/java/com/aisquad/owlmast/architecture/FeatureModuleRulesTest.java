package com.aisquad.owlmast.architecture;

import static org.assertj.core.api.Assertions.assertThat;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.lang.ArchRule;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;

/** Production code must satisfy every feature-module rule (AC2). */
class FeatureModuleRulesTest {

  static final String ROOT = "com.aisquad.owlmast";
  private static final FeatureModuleRules RULES = FeatureModuleRules.forRoot(ROOT);
  private static JavaClasses production;

  @BeforeAll
  static void importProductionClasses() {
    production =
        new ClassFileImporter()
            .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
            .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TEST_FIXTURES)
            .importPackages(ROOT);
  }

  @Test
  void productionClassesAreImported() {
    assertThat(production).isNotEmpty();
    assertThat(RULES.features(production)).contains("bootstrap").doesNotContain("archfixtures");
  }

  @TestFactory
  Stream<DynamicTest> rules() {
    return Stream.concat(
            RULES.staticRules().stream(), RULES.featureIsolationRules(production).stream())
        .map(rule -> DynamicTest.dynamicTest(rule.getDescription(), () -> check(rule)));
  }

  private static void check(ArchRule rule) {
    rule.check(production);
  }
}
