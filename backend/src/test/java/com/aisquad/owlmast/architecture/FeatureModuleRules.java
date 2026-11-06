package com.aisquad.owlmast.architecture;

import static com.tngtech.archunit.base.DescribedPredicate.not;
import static com.tngtech.archunit.core.domain.JavaClass.Predicates.resideInAPackage;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.base.DescribedPredicate;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.domain.JavaMethodCall;
import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.lang.EvaluationResult;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.reactivestreams.Publisher;

/**
 * Module and reactive rules for a feature-packaged root (AD-2, AD-5, AD-16). The same rules are
 * evaluated against production code and against deliberately broken fixtures.
 */
public final class FeatureModuleRules {

  static final String PLATFORM = "platform";
  private static final Set<String> BLOCKING_METHODS =
      Set.of("block", "blockFirst", "blockLast", "blockOptional", "toFuture", "toStream");

  private final String root;

  private FeatureModuleRules(String root) {
    this.root = root;
  }

  public static FeatureModuleRules forRoot(String root) {
    return new FeatureModuleRules(root);
  }

  /** Rules that do not depend on which features exist. */
  public List<ArchRule> staticRules() {
    return List.of(
        noClasses()
            .that()
            .resideInAPackage(pkg(PLATFORM, ".."))
            .should()
            .dependOnClassesThat(
                resideInAPackage(root + "..").and(not(resideInAPackage(pkg(PLATFORM, "..")))))
            .as("platform must not depend on feature packages"),
        slices()
            .matching(root + ".(*)..")
            .should()
            .beFreeOfCycles()
            .as("feature packages must be free of dependency cycles"),
        noClasses()
            .that()
            .resideInAPackage(root + "..")
            .should()
            .dependOnClassesThat()
            .areAssignableTo(ThreadLocal.class)
            .as("ThreadLocal must not carry authorization or tenant state (AD-5)"),
        noClasses()
            .that()
            .resideInAnyPackage(root + "..api..", root + "..application..", root + "..domain..")
            .should()
            .callMethodWhere(blockingPublisherCall())
            .as("api/application/domain must not block on publishers"),
        noClasses()
            .that()
            .resideInAnyPackage(root + "..api..", root + "..domain..")
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage("org.springframework..", root + "..adapter..")
            .as("api/domain stay free of Spring and adapters"),
        noClasses()
            .that()
            .resideInAnyPackage(root + "..application..", root + "..port..")
            .should()
            .dependOnClassesThat()
            .resideInAPackage(root + "..adapter..")
            .as("application/port must not depend on adapters"));
  }

  /** Each feature's non-api internals are private to that feature. */
  public List<ArchRule> featureIsolationRules(JavaClasses classes) {
    return features(classes).stream().map(this::featureInternalsPrivate).toList();
  }

  /** Every rule evaluated separately, keyed by its description, so each report stays readable. */
  public Map<String, EvaluationResult> evaluateAll(JavaClasses classes) {
    return Stream.concat(staticRules().stream(), featureIsolationRules(classes).stream())
        .collect(
            Collectors.toMap(
                ArchRule::getDescription,
                rule -> rule.evaluate(classes),
                (left, right) -> left,
                LinkedHashMap::new));
  }

  private ArchRule featureInternalsPrivate(String feature) {
    String featurePkg = pkg(feature, "..");
    String apiPkg = pkg(feature, ".api..");
    return noClasses()
        .that(resideInAPackage(root + "..").and(not(resideInAPackage(featurePkg))))
        .should()
        .dependOnClassesThat(resideInAPackage(featurePkg).and(not(resideInAPackage(apiPkg))))
        .as("only '" + feature + ".api' may be used outside feature '" + feature + "'");
  }

  Set<String> features(JavaClasses classes) {
    String prefix = root + ".";
    return classes.stream()
        .map(JavaClass::getPackageName)
        .filter(name -> name.startsWith(prefix))
        .map(name -> name.substring(prefix.length()).split("\\.", 2)[0])
        .filter(name -> !name.isEmpty() && !name.equals(PLATFORM))
        .collect(Collectors.toUnmodifiableSet());
  }

  private String pkg(String segment, String suffix) {
    return root + "." + segment + suffix;
  }

  private static DescribedPredicate<JavaMethodCall> blockingPublisherCall() {
    return new DescribedPredicate<>("blocking call on a reactive publisher") {
      @Override
      public boolean test(JavaMethodCall call) {
        return call.getTarget().getOwner().isAssignableTo(Publisher.class)
            && BLOCKING_METHODS.contains(call.getTarget().getName());
      }
    };
  }
}
