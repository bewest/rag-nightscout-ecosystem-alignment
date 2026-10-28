-- 0002: tenant_members identifies a person by identity provider and subject.
--
-- Decided 2026-10-27 (maintainer; execution plan §2.13, "Two schema answers"):
-- two text columns, unique together, with no foreign key to any identity table
-- of Nightscout's, so a Kratos, Clerk or any OIDC subject fits (D17 as amended).
-- Uniqueness is per tenant: one person may be a member of several tenants.
-- The column keeps the seam's name, subject_id, so seam code still reads it.
--
-- Existing rows have no provider, and which provider issued them is not
-- recorded anywhere. The migration therefore refuses to run while the table
-- holds rows, rather than guess (open question in the schema spec). The check
-- lifts FORCE for its one count: tenant_members is FORCE-RLS, so the owning
-- role would otherwise count zero rows whatever the table holds.

ALTER TABLE tenant_members NO FORCE ROW LEVEL SECURITY;
DO $$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM tenant_members;
  IF n > 0 THEN
    RAISE EXCEPTION '0002: tenant_members has % rows; record each row''s identity provider before migrating', n
      USING ERRCODE = '55000';
  END IF;
END $$;
ALTER TABLE tenant_members FORCE ROW LEVEL SECURITY;

ALTER TABLE tenant_members
  ADD COLUMN provider text NOT NULL
      CONSTRAINT tenant_members_provider_format CHECK (provider ~ '^[a-z][a-z0-9-]{0,31}$'),
  ALTER COLUMN subject_id TYPE text USING subject_id::text,
  ADD CONSTRAINT tenant_members_subject_length CHECK (length(subject_id) BETWEEN 1 AND 255),
  DROP CONSTRAINT tenant_members_tenant_id_subject_id_key,
  ADD CONSTRAINT tenant_members_identity UNIQUE (tenant_id, provider, subject_id);
