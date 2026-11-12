-- E01 retrospective B1 (E01-R-04): a work item stored under a blank tenant id (empty or only white
-- space, which is what the application's TenantId refuses) cannot be bound to a
-- tenant scope, so it can never be claimed, and before this change it failed tenant discovery for
-- every tenant. The jobs module owns this table (V002).
--
-- NOT VALID first: the check then holds for every row written from now on without the migration
-- failing, and with it the whole startup, on a database that already holds such a row. It is
-- validated in the same migration when no stored row breaks it. Otherwise it stays NOT VALID (still
-- enforced for new and updated rows), a warning names the count, and discovery skips those rows
-- with a log line until an operator corrects them and runs
--   ALTER TABLE jobs.work_item VALIDATE CONSTRAINT work_item_tenant_id_not_blank;

ALTER TABLE jobs.work_item
    ADD CONSTRAINT work_item_tenant_id_not_blank CHECK (tenant_id !~ '^[[:space:]]*$') NOT VALID;

DO $$
DECLARE
    blank_rows bigint;
BEGIN
    SELECT count(*) INTO blank_rows FROM jobs.work_item WHERE tenant_id ~ '^[[:space:]]*$';
    IF blank_rows = 0 THEN
        ALTER TABLE jobs.work_item VALIDATE CONSTRAINT work_item_tenant_id_not_blank;
    ELSE
        RAISE WARNING 'jobs.work_item holds % row(s) with a blank tenant_id; work_item_tenant_id_not_blank stays NOT VALID until they are corrected', blank_rows;
    END IF;
END
$$;
