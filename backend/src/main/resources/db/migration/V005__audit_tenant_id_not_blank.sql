-- E01 retrospective B1 (E01-R-04): audit rows are read only under a bound tenant scope, so a row
-- with a blank tenant id is invisible to every history query and can never be published. The audit
-- module owns these tables (V003). Same shape as V004: NOT VALID first, validated here when no
-- stored row breaks the check, otherwise left NOT VALID (still enforced for new and updated rows)
-- with a warning, to be validated by an operator after correcting the rows:
--   ALTER TABLE audit.publication_intent VALIDATE CONSTRAINT publication_intent_tenant_id_not_blank;
--   ALTER TABLE audit.event VALIDATE CONSTRAINT event_tenant_id_not_blank;

ALTER TABLE audit.publication_intent
    ADD CONSTRAINT publication_intent_tenant_id_not_blank CHECK (tenant_id !~ '^[[:space:]]*$') NOT VALID;

ALTER TABLE audit.event
    ADD CONSTRAINT event_tenant_id_not_blank CHECK (tenant_id !~ '^[[:space:]]*$') NOT VALID;

DO $$
DECLARE
    blank_rows bigint;
BEGIN
    SELECT count(*) INTO blank_rows FROM audit.publication_intent WHERE tenant_id ~ '^[[:space:]]*$';
    IF blank_rows = 0 THEN
        ALTER TABLE audit.publication_intent VALIDATE CONSTRAINT publication_intent_tenant_id_not_blank;
    ELSE
        RAISE WARNING 'audit.publication_intent holds % row(s) with a blank tenant_id; publication_intent_tenant_id_not_blank stays NOT VALID until they are corrected', blank_rows;
    END IF;
    SELECT count(*) INTO blank_rows FROM audit.event WHERE tenant_id ~ '^[[:space:]]*$';
    IF blank_rows = 0 THEN
        ALTER TABLE audit.event VALIDATE CONSTRAINT event_tenant_id_not_blank;
    ELSE
        RAISE WARNING 'audit.event holds % row(s) with a blank tenant_id; event_tenant_id_not_blank stays NOT VALID until they are corrected', blank_rows;
    END IF;
END
$$;
