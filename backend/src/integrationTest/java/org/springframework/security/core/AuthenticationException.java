package org.springframework.security.core;

/**
 * Test-only stand-in with the fully qualified name of Spring Security's exception, which is not a
 * dependency before E02. {@code UnhandledFailureIT} uses it to prove the name guard of {@code
 * UnhandledFailureAdvice}; delete it when the real class is on the classpath.
 */
public abstract class AuthenticationException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  protected AuthenticationException(String message) {
    super(message);
  }
}
