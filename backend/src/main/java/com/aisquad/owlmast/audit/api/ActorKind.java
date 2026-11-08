package com.aisquad.owlmast.audit.api;

/** Who acted (envelope v1; vocabulary shared with OM-16.01). */
public enum ActorKind {
  /** A person acting through a browser or client they own. */
  HUMAN,
  /** A Claude/Codex agent acting under an enrolled person's delegated scope. */
  AGENT,
  /** The Owl Mast backend acting for a tenant, for example a background processor. */
  SERVICE,
  /** A platform or infrastructure component outside any tenant actor, such as a migration. */
  SYSTEM
}
