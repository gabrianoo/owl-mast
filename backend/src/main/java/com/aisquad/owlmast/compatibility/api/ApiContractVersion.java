package com.aisquad.owlmast.compatibility.api;

/**
 * Version of the public API contract. Minor versions only add; a major bump marks a breaking
 * change. Consumers decide compatibility (equal major, minor at or above their minimum).
 */
public record ApiContractVersion(int major, int minor) {

  public ApiContractVersion {
    if (major < 0 || minor < 0) {
      throw new IllegalArgumentException("API contract major and minor must be non-negative");
    }
  }

  /** The {@code major.minor} label used in diagnostics and documentation. */
  public String label() {
    return major + "." + minor;
  }
}
