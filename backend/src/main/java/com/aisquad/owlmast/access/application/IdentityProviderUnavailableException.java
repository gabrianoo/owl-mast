package com.aisquad.owlmast.access.application;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

/**
 * The identity provider could not be reached or did not answer as an identity provider. It is an
 * outage, not a judgement about a credential: callers answer 5xx and keep an existing session. The
 * message is fixed text; the provider's answer is never carried. The common error envelope reads
 * the status from the annotation and nothing else.
 */
@ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
public final class IdentityProviderUnavailableException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  public IdentityProviderUnavailableException(Throwable cause) {
    super("The identity provider is unavailable", cause);
  }
}
