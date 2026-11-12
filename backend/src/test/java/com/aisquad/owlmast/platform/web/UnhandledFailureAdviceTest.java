package com.aisquad.owlmast.platform.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.blocking.BlockingCapacityExceededException;
import com.aisquad.owlmast.platform.blocking.BlockingDeadlineExceededException;
import com.aisquad.owlmast.platform.persistence.IncompatibleScopeException;
import com.aisquad.owlmast.platform.persistence.ScopeBindingUnavailableException;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import java.lang.reflect.Modifier;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.annotation.ResponseStatus;

/**
 * E01-R-05: the status table of the shared kernel's failures. Several of these exceptions can only
 * be raised by the kernel itself (package-private constructors), so the table is checked as data
 * here; {@code UnhandledFailureIT} raises the denial, the missing scope and both bounded-blocking
 * failures through the real code and reads the answer.
 */
class UnhandledFailureAdviceTest {

  @Test
  void everyPlatformFailureHasItsDecidedStatus() {
    assertThat(UnhandledFailureAdvice.STATUS_BY_PLATFORM_FAILURE)
        .containsExactlyInAnyOrderEntriesOf(
            Map.of(
                OperationDeniedException.class, HttpStatus.FORBIDDEN,
                MissingScopeException.class, HttpStatus.INTERNAL_SERVER_ERROR,
                IncompatibleScopeException.class, HttpStatus.INTERNAL_SERVER_ERROR,
                ScopeBindingUnavailableException.class, HttpStatus.INTERNAL_SERVER_ERROR,
                BlockingCapacityExceededException.class, HttpStatus.SERVICE_UNAVAILABLE,
                BlockingDeadlineExceededException.class, HttpStatus.GATEWAY_TIMEOUT));
  }

  /**
   * Review 5883535263: the table above only restates the decision, so a new failure type in the
   * shared kernel would silently answer 500. Every throwable the kernel declares must have a
   * decided status: an entry in the table, or (for a web failure) a status of its own.
   */
  @Test
  void everyFailureTheSharedKernelDeclaresHasADecidedStatus() {
    List<String> undecided =
        new ClassFileImporter()
                .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
                .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TEST_FIXTURES)
                .importPackages("com.aisquad.owlmast.platform")
                .stream()
                .filter(type -> type.isAssignableTo(Throwable.class))
                .map(JavaClass::reflect)
                .filter(
                    type -> !UnhandledFailureAdvice.STATUS_BY_PLATFORM_FAILURE.containsKey(type))
                .filter(type -> !ErrorResponse.class.isAssignableFrom(type))
                .filter(type -> !type.isAnnotationPresent(ResponseStatus.class))
                .map(Class::getName)
                .toList();
    assertThat(undecided)
        .as("add each to STATUS_BY_PLATFORM_FAILURE with its decided status")
        .isEmpty();
  }

  /** The table is looked up by exact class, which is only complete while every entry is final. */
  @Test
  void everyMappedPlatformFailureIsFinal() {
    assertThat(UnhandledFailureAdvice.STATUS_BY_PLATFORM_FAILURE.keySet())
        .allSatisfy(type ->
            assertThat(Modifier.isFinal(type.getModifiers()))
                .as("%s must be final, or the lookup must walk its superclasses", type)
                .isTrue());
  }

  @Test
  void aDenialAnswersForbiddenAndAnUnknownFailureStaysAServerError() {
    assertThat(UnhandledFailureAdvice.statusOf(new OperationDeniedException("not-permitted")))
        .isEqualTo(HttpStatus.FORBIDDEN);
    assertThat(UnhandledFailureAdvice.statusOf(new MissingScopeException()))
        .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
    assertThat(UnhandledFailureAdvice.statusOf(new IllegalStateException("anything else")))
        .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
    // The status is read from the failure itself, not from its cause.
    assertThat(
            UnhandledFailureAdvice.statusOf(
                new IllegalStateException(new OperationDeniedException("not-permitted"))))
        .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
  }
}
