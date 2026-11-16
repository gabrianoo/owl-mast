-- OM-02.01: access-owned identity binding (AD-3). Only the access module reads or writes it.
-- A principal is the pair (issuer, subject) of the trusted identity provider. Display name, username
-- and email are never identity and are deliberately not stored; no credential is stored either.
-- tenant_id is the installation's configured tenant until OM-02.02 supplies tenant membership.

CREATE SCHEMA IF NOT EXISTS access;

CREATE TABLE access.principal (
    principal_id    uuid        PRIMARY KEY,
    tenant_id       text        NOT NULL CHECK (tenant_id !~ '^[[:space:]]*$'),
    issuer          text        NOT NULL CHECK (issuer <> '' AND length(issuer) <= 2048),
    subject         text        NOT NULL CHECK (subject <> '' AND length(subject) <= 255),
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_sign_in_at timestamptz,
    sign_in_count   bigint      NOT NULL DEFAULT 0 CHECK (sign_in_count >= 0),
    CONSTRAINT principal_identity_key UNIQUE (tenant_id, issuer, subject)
);
