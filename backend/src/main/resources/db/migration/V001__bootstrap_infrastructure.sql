-- OM-01.01: bootstrap-owned infrastructure only (AD-2). Feature schemas arrive with their owning stories.
-- VectorChord is required; pgvector is allowed solely as its dependency (AD-7).

CREATE EXTENSION IF NOT EXISTS vchord CASCADE;

CREATE SCHEMA IF NOT EXISTS bootstrap;

CREATE TABLE bootstrap.schema_baseline (
    id             smallint PRIMARY KEY CHECK (id = 1),
    vchord_version text NOT NULL,
    vector_version text NOT NULL,
    applied_at     timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bootstrap.schema_baseline (id, vchord_version, vector_version)
SELECT 1, vchord.extversion, vector.extversion
FROM pg_extension AS vchord, pg_extension AS vector
WHERE vchord.extname = 'vchord' AND vector.extname = 'vector';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM bootstrap.schema_baseline WHERE id = 1) THEN
        RAISE EXCEPTION 'Owl Mast bootstrap requires the vchord extension and its vector dependency to be installed in this database';
    END IF;
END
$$;
