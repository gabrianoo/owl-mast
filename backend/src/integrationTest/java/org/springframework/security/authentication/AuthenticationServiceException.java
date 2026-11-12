package org.springframework.security.authentication;

import org.springframework.security.core.AuthenticationException;

/**
 * Test-only stand-in with the fully qualified name of Spring Security's exception, which is not a
 * dependency before E02. {@code UnhandledFailureIT} uses it to prove the name guard of {@code
 * UnhandledFailureAdvice}; delete it when the real class is on the classpath.
 */
public class AuthenticationServiceException extends AuthenticationException {

  private static final long serialVersionUID = 1L;

  public AuthenticationServiceException(String message) {
    super(message);
  }
}
