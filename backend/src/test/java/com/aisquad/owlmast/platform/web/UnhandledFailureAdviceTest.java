package com.aisquad.owlmast.platform.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.aisquad.owlmast.platform.authorization.OperationDeniedException;
import com.aisquad.owlmast.platform.blocking.BlockingCapacityExceededException;
import com.aisquad.owlmast.platform.blocking.BlockingDeadlineExceededException;
import com.aisquad.owlmast.platform.persistence.IncompatibleScopeException;
import com.aisquad.owlmast.platform.persistence.ScopeBindingUnavailableException;
import com.aisquad.owlmast.platform.scope.MissingScopeException;
import java.lang.reflect.Modifier;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

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
