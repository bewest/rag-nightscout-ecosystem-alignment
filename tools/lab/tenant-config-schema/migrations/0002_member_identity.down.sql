-- 0002 down. Fails if any subject is not a UUID (the seam's original type).
ALTER TABLE tenant_members
  DROP CONSTRAINT tenant_members_identity,
  DROP CONSTRAINT tenant_members_subject_length,
  ALTER COLUMN subject_id TYPE uuid USING subject_id::uuid,
  ADD CONSTRAINT tenant_members_tenant_id_subject_id_key UNIQUE (tenant_id, subject_id),
  DROP COLUMN provider;
