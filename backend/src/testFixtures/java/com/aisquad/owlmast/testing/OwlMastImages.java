package com.aisquad.owlmast.testing;

import org.testcontainers.utility.DockerImageName;

/** Pinned container images qualified by OM-01.01-T1 (docs/toolchain-qualification.md). */
public final class OwlMastImages {

  /** PostgreSQL 18.3 with VectorChord 1.1.1 and its pgvector 0.8.2 dependency preloaded. */
  public static final DockerImageName VECTORCHORD_POSTGRES =
      DockerImageName.parse(
              "tensorchord/vchord-postgres:pg18-v1.1.1"
                  + "@sha256:700ff05ebdc7e4afd4dd8442e0684293046c3833677fec326550000a04cf8a91")
          .asCompatibleSubstituteFor("postgres");

  /** Plain PostgreSQL without VectorChord, used only to prove explicit extension failures. */
  public static final DockerImageName PLAIN_POSTGRES =
      DockerImageName.parse(
              "postgres:18.2-alpine"
                  + "@sha256:035b9ab53cfa147d7202b61f5f7782b939ae815b7d6bc81c96b7b42ff1fca950")
          .asCompatibleSubstituteFor("postgres");

  /**
   * Keycloak 26.8.2, the image and digest the installation chart pins ({@code
   * identity.keycloak.image}); a deploy test keeps the two equal. Used for the synthetic realm of
   * the sign-in tests (OM-02.01).
   */
  public static final DockerImageName KEYCLOAK =
      DockerImageName.parse(
          "quay.io/keycloak/keycloak:26.8.2"
              + "@sha256:3879c623248408de29a5303178b5816c77e8dfef3890c361f8c0bbeaa979ba3b");

  private OwlMastImages() {}
}
