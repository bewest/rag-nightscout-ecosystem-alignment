-- GENERATED FILE — do not edit.
--
-- PostgreSQL DDL for the Nightscout `devicestatus` collection, multitenant shape.
--
-- Source:   aid-devicestatus-2025.yaml
-- Evidence: reports/schema-census/devicestatus.census.json
-- Indexes:  lib/server/devicestatus.js:182 (indexedFields, on chore/nightscout-modernization)
-- Emitter:  tools/nsschema/emit/postgres_emit.py
--
-- Regenerate with: make schema-emit
--
-- THE COLUMNS BELOW ARE AN INDEX ACCELERATOR. THE DOCUMENT IS THE RECORD.
-- Dropping every generated column must not change an answer. In particular an
-- `$exists` check must read `doc #> '{path}'` and never a column: a column is
-- built from `->>`, which returns SQL NULL for an absent key and for an explicit
-- JSON null alike, and cannot tell them apart. lib/storage/filter.js does this
-- correctly; nothing here licenses a hand-written query to do otherwise.
--
-- Indexed fields with no column, and why:
--   NSCLIENT_ID              UNDECLARED  the model does not declare this field
--   date                     UNDECLARED  the model does not declare this field

CREATE TABLE devicestatus (
  -- tenant_id leads the table and every index below: under RLS the policy
  -- predicate is an ordinary equality, and the planner can only build index
  -- bounds from it if it is the leading column.
  tenant_id  uuid   NOT NULL,
  doc        jsonb  NOT NULL,
  "_id"        text NOT NULL
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{_id}') = 'string' THEN (doc #>> '{_id}') END) STORED,
  "created_at" text
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{created_at}') = 'string' THEN (doc #>> '{created_at}') END) STORED,
  "identifier" text
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{identifier}') = 'string' THEN (doc #>> '{identifier}') END) STORED,

  -- Scoped to the tenant rather than global: two tenants restored from
  -- different deployments can legitimately carry the same _id, and a
  -- global unique constraint would make one of them unimportable.
  PRIMARY KEY (tenant_id, "_id")
);

CREATE INDEX devicestatus_tenant_created_at
  ON devicestatus (tenant_id, "created_at" ASC);
CREATE INDEX devicestatus_tenant_nsclient_id
  ON devicestatus (tenant_id, (doc #>> '{NSCLIENT_ID}') ASC);
CREATE INDEX devicestatus_tenant_created_at_identifier_date
  ON devicestatus (tenant_id, "created_at" DESC, "identifier" DESC, (doc #>> '{date}') DESC);

-- FORCE is the load-bearing word: without it the table OWNER bypasses the
-- policy. It still does not subject a SUPERUSER — BYPASSRLS is implicit for
-- one — so anything verifying isolation must connect as a role that is
-- NOSUPERUSER NOBYPASSRLS, or it has verified nothing.
ALTER TABLE devicestatus ENABLE ROW LEVEL SECURITY;
ALTER TABLE devicestatus FORCE ROW LEVEL SECURITY;

-- NULLIF so that an unbound connection yields NULL rather than an empty
-- string, and `tenant_id = NULL` is never true: the fail-closed property
-- D3 is chosen for. WITH CHECK is what extends it to writes, which is the
-- axis MongoDB's role-keyed views cannot cover at all ({M} §6.7).
CREATE POLICY devicestatus_tenant_isolation ON devicestatus
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
