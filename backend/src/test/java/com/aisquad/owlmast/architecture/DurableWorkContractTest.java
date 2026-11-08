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
import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import java.io.IOException;
import java.lang.reflect.RecordComponent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * AC9 compatibility and module-rule tests: the contract document names every published field,
 * vocabulary constant and version; wake-ups come only from in-process Spring scheduling in one
 * adapter package; and no broker, external scheduler or worker-service client is on the classpath.
 */
class DurableWorkContractTest {

  private static final Path CONTRACT = Path.of("..", "docs", "durable-work-and-audit-contract.md");
  private static final Path LOCKFILE = Path.of("gradle.lockfile");
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
          "db-scheduler");

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
}
