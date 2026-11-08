package com.aisquad.owlmast.architecture;

import static com.tngtech.archunit.core.domain.properties.CanBeAnnotated.Predicates.annotatedWith;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.audit.api.ActorKind;
import com.aisquad.owlmast.audit.api.AuditEnvelope;
import com.aisquad.owlmast.audit.api.AuditEnvelopeContract;
import com.aisquad.owlmast.audit.api.AuditOutcome;
import com.aisquad.owlmast.jobs.api.DispatchDecision;
import com.aisquad.owlmast.jobs.api.WorkItem;
import com.aisquad.owlmast.jobs.api.WorkItemContract;
import com.aisquad.owlmast.jobs.api.WorkStatus;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import java.io.IOException;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * AC9 compatibility and module-rule tests: the published v1 shape of both contracts is frozen in
 * {@code contract/contract-shape-v1.txt}; the contract document names every published field,
 * vocabulary constant and version; wake-ups come only from in-process Spring scheduling in one
 * adapter package; and no broker, external scheduler, worker-service client or connection pool is
 * on the classpath.
 */
class DurableWorkContractTest {

  private static final Path CONTRACT = Path.of("..", "docs", "durable-work-and-audit-contract.md");
  private static final Path LOCKFILE = Path.of("gradle.lockfile");
  private static final Path FROZEN_SHAPE =
      Path.of("src", "test", "resources", "contract", "contract-shape-v1.txt");
  private static final Path ACTUAL_SHAPE = Path.of("build", "contract-shape-actual.txt");
  private static final List<String> CONTRACT_PACKAGES =
      List.of("com.aisquad.owlmast.jobs.api", "com.aisquad.owlmast.audit.api");
  private static final List<String> FORBIDDEN_DEPENDENCIES =
      List.of(
          "spring-kafka",
          "kafka-clients",
          "spring-amqp",
          "spring-rabbit",
          "amqp-client",
          "artemis",
          "jakarta.jms",
          "quartz",
          "temporal",
          "restate",
          "spring-cloud-stream",
          "pulsar",
          "jobrunr",
          "db-scheduler",
          // The separate audit outcome path takes a second connection per concurrent failure; a
          // pool must be introduced deliberately with headroom for it (contract, durability step
          // 5).
          "io.r2dbc:r2dbc-pool");

  private static String contract;
  private static JavaClasses production;

  @BeforeAll
  static void load() throws IOException {
    contract = Files.readString(CONTRACT);
    production =
        new ClassFileImporter()
            .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
            .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TEST_FIXTURES)
            .importPackages(FeatureModuleRulesTest.ROOT);
  }

  @Test
  void contractDocumentStatesTheCurrentVersions() {
    assertThat(contract)
        .contains("WorkItemContract.VERSION = " + WorkItemContract.VERSION)
        .contains("AuditEnvelopeContract.VERSION = " + AuditEnvelopeContract.VERSION)
        .contains("`" + AuditEnvelopeContract.PUBLISH_WORK_TYPE.value() + "`")
        .contains("| `max-attempts` | " + WorkItemContract.DEFAULT_MAX_ATTEMPTS + " |")
        .contains("| `backoff-base` | " + WorkItemContract.DEFAULT_BACKOFF_BASE + " |")
        .contains("| `backoff-cap` | " + WorkItemContract.DEFAULT_BACKOFF_CAP + " |")
        .contains("| `lease-duration` | " + WorkItemContract.DEFAULT_LEASE_DURATION + " |")
        .contains("| `claim-batch-size` | " + WorkItemContract.DEFAULT_CLAIM_BATCH_SIZE + " |")
        .contains("| `poll-interval` | " + WorkItemContract.DEFAULT_POLL_INTERVAL + " |");
  }

  @Test
  void contractDocumentNamesEveryEnvelopeFieldAndWorkItemComponent() {
    Stream.of(AuditEnvelope.class, WorkItem.class)
        .flatMap(type -> Arrays.stream(type.getRecordComponents()))
        .map(RecordComponent::getName)
        .forEach(component ->
            assertThat(contract)
                .as("contract document names component '%s'", component)
                .contains("`" + component + "`"));
  }

  @Test
  void contractDocumentNamesEveryVocabularyConstant() {
    Stream.of(
            WorkStatus.values(),
            DispatchDecision.values(),
            ActorKind.values(),
            AuditOutcome.values())
        .flatMap(Arrays::stream)
        .map(Enum::name)
        .forEach(constant ->
            assertThat(contract)
                .as("contract document names vocabulary constant '%s'", constant)
                .contains("`" + constant + "`"));
  }

  @Test
  void processorsAreWokenOnlyByInProcessSpringSchedulingInOneAdapter() {
    String scheduling = FeatureModuleRulesTest.ROOT + ".jobs.adapter.scheduling..";
    classes()
        .that()
        .areAnnotatedWith(EnableScheduling.class)
        .or()
        .containAnyMethodsThat(annotatedWith(Scheduled.class))
        .should()
        .resideInAPackage(scheduling)
        .as("scheduling annotations live only in jobs.adapter.scheduling")
        .check(production);
    classes()
        .that()
        .resideInAPackage(scheduling)
        .and()
        .containAnyMethodsThat(annotatedWith(Scheduled.class))
        .should()
        .haveSimpleName("WorkScheduler")
        .as("exactly one wake-up source exists")
        .check(production);
    noClasses()
        .that()
        .resideInAPackage(FeatureModuleRulesTest.ROOT + "..")
        .should()
        .dependOnClassesThat()
        .resideInAnyPackage(
            "org.springframework.kafka..",
            "org.apache.kafka..",
            "org.springframework.amqp..",
            "com.rabbitmq..",
            "jakarta.jms..",
            "org.quartz..",
            "io.temporal..",
            "dev.restate..")
        .as("no broker, external scheduler or workflow-engine client (AD-6)")
        .check(production);
  }

  @Test
  void noBrokerOrWorkerServiceDependencyIsLocked() throws IOException {
    List<String> locked =
        Files.readAllLines(LOCKFILE).stream().filter(line -> !line.startsWith("#")).toList();
    for (String forbidden : FORBIDDEN_DEPENDENCIES) {
      assertThat(locked)
          .as("dependency lockfile must not contain '%s'", forbidden)
          .noneMatch(line -> line.toLowerCase(java.util.Locale.ROOT).contains(forbidden));
    }
  }

  /**
   * The v1 shape of every published type, one line per member: record components (position, name,
   * generic type), enum constants (position), sealed permits, public constructors, public static
   * and instance methods (including derived ones such as {@code WorkItem.idempotencyKey()}) and
   * published constants. Removing, renaming or retyping any of them removes a frozen line and fails
   * here; the compatibility rule then requires a new contract version and a new frozen file rather
   * than an edit of this one. Additions are permitted within v1 only with an absence-preserving
   * meaning and are appended to the frozen file in the same change, so no frozen line is edited.
   * The actual shape is written to {@code build/contract-shape-actual.txt}.
   */
  @Test
  void thePublishedVersionOneShapeIsFrozen() throws IOException {
    List<String> actual = publishedShape();
    Files.createDirectories(ACTUAL_SHAPE.getParent());
    Files.write(ACTUAL_SHAPE, actual, StandardCharsets.UTF_8);
    List<String> frozen =
        Files.readAllLines(FROZEN_SHAPE, StandardCharsets.UTF_8).stream()
            .filter(line -> !line.isBlank() && !line.startsWith("#"))
            .toList();

    assertThat(actual)
        .as("every frozen v1 line must still hold (removal, rename or retype needs a new version)")
        .containsAll(frozen);
    assertThat(frozen)
        .as("every published line must be frozen; record additions in the frozen file")
        .containsAll(actual);
  }

  @Test
  void theFrozenShapeBelongsToTheCurrentContractVersions() throws IOException {
    assertThat(Files.readAllLines(FROZEN_SHAPE, StandardCharsets.UTF_8))
        .as("a new contract version needs its own frozen shape file")
        .contains(
            "# work-item contract version "
                + WorkItemContract.VERSION
                + ", audit-envelope contract version "
                + AuditEnvelopeContract.VERSION);
  }

  private static List<String> publishedShape() {
    return production.stream()
        .filter(type -> CONTRACT_PACKAGES.contains(type.getPackageName()))
        .filter(type ->
            type.getModifiers().contains(com.tngtech.archunit.core.domain.JavaModifier.PUBLIC))
        .map(JavaClass::reflect)
        .flatMap(DurableWorkContractTest::shapeOf)
        .sorted()
        .toList();
  }

  private static Stream<String> shapeOf(Class<?> type) {
    String name = type.getName();
    Stream.Builder<String> lines = Stream.builder();
    if (type.isRecord()) {
      RecordComponent[] components = type.getRecordComponents();
      for (int index = 0; index < components.length; index++) {
        lines.add(
            "record "
                + name
                + " component "
                + index
                + " "
                + components[index].getName()
                + ": "
                + components[index].getGenericType().getTypeName());
      }
    } else if (type.isEnum()) {
      Object[] constants = type.getEnumConstants();
      for (int index = 0; index < constants.length; index++) {
        lines.add("enum " + name + " constant " + index + " " + constants[index]);
      }
    } else if (type.isInterface()) {
      lines.add("interface " + name);
    } else {
      lines.add("class " + name);
    }
    if (type.isSealed()) {
      Arrays.stream(type.getPermittedSubclasses())
          .map(Class::getName)
          .forEach(permitted -> lines.add("sealed " + name + " permits " + permitted));
    }
    Arrays.stream(type.getDeclaredConstructors())
        .filter(constructor -> Modifier.isPublic(constructor.getModifiers()))
        .filter(constructor -> !constructor.isSynthetic())
        .map(constructor ->
            "constructor "
                + name
                + "("
                + Arrays.stream(constructor.getGenericParameterTypes())
                    .map(Type::getTypeName)
                    .collect(Collectors.joining(", "))
                + ")")
        .forEach(lines::add);
    Arrays.stream(type.getDeclaredMethods())
        .filter(method -> Modifier.isPublic(method.getModifiers()))
        .filter(method -> !method.isSynthetic() && !method.isBridge())
        .filter(method -> !isGenerated(type, method))
        .map(method ->
            "method "
                + name
                + (Modifier.isStatic(method.getModifiers()) ? " static " : " ")
                + signature(method))
        .forEach(lines::add);
    Arrays.stream(type.getDeclaredFields())
        .filter(DurableWorkContractTest::isPublishedConstant)
        .filter(field -> !field.isEnumConstant())
        .map(field -> "constant " + name + "." + field.getName() + " = " + valueOf(field))
        .forEach(lines::add);
    return lines.build();
  }

  /** Members the compiler derives from the shape already recorded above. */
  private static boolean isGenerated(Class<?> type, Method method) {
    String member = method.getName();
    int arity = method.getParameterCount();
    if (List.of("equals", "hashCode", "toString").contains(member)) {
      return true;
    }
    if (type.isEnum() && (member.equals("values") || member.equals("valueOf"))) {
      return true;
    }
    return type.isRecord()
        && arity == 0
        && Arrays.stream(type.getRecordComponents()).anyMatch(c -> c.getName().equals(member));
  }

  private static String signature(Method method) {
    return method.getName()
        + "("
        + Arrays.stream(method.getGenericParameterTypes())
            .map(Type::getTypeName)
            .collect(Collectors.joining(", "))
        + "): "
        + method.getGenericReturnType().getTypeName();
  }

  private static boolean isPublishedConstant(Field field) {
    int modifiers = field.getModifiers();
    return Modifier.isPublic(modifiers)
        && Modifier.isStatic(modifiers)
        && Modifier.isFinal(modifiers);
  }

  private static String valueOf(Field field) {
    try {
      return Objects.toString(field.get(null));
    } catch (IllegalAccessException inaccessible) {
      throw new IllegalStateException(inaccessible);
    }
  }
}
