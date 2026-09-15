-- GENERATED FILE — do not edit.
--
-- PostgreSQL DDL for the Nightscout `treatments` collection, multitenant shape.
--
-- Source:   aid-treatments-2025.yaml
-- Evidence: reports/schema-census/treatments.census.json
-- Indexes:  lib/server/treatments.js:443 (indexedFields, on chore/nightscout-modernization)
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
--   boluscalc.foods._id      MULTIKEY    traverses an array; no column, no index, capability lost until decomposition
--   NSCLIENT_ID              UNDECLARED  the model does not declare this field
--   date                     UNDECLARED  the model does not declare this field

CREATE TABLE treatments (
  -- tenant_id leads the table and every index below: under RLS the policy
  -- predicate is an ordinary equality, and the planner can only build index
  -- bounds from it if it is the leading column.
  tenant_id  uuid   NOT NULL,
  doc        jsonb  NOT NULL,
  "_id"        text NOT NULL
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{_id}') = 'string' THEN (doc #>> '{_id}') END) STORED,
  "created_at" text
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{created_at}') = 'string' THEN (doc #>> '{created_at}') END) STORED,
  "eventType"  text
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{eventType}') = 'string' THEN (doc #>> '{eventType}') END) STORED,
  "insulin"    numeric
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{insulin}') = 'number' THEN (doc #>> '{insulin}')::numeric END) STORED,
  "carbs"      numeric
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{carbs}') = 'number' THEN (doc #>> '{carbs}')::numeric END) STORED,
  "glucose"    numeric
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{glucose}') = 'number' THEN (doc #>> '{glucose}')::numeric END) STORED,
  "enteredBy"  text
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{enteredBy}') = 'string' THEN (doc #>> '{enteredBy}') END) STORED,
  "notes"      text
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{notes}') = 'string' THEN (doc #>> '{notes}') END) STORED,
  "percent"    numeric
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{percent}') = 'number' THEN (doc #>> '{percent}')::numeric END) STORED,
  "absolute"   numeric
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{absolute}') = 'number' THEN (doc #>> '{absolute}')::numeric END) STORED,
  "duration"   numeric
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{duration}') = 'number' THEN (doc #>> '{duration}')::numeric END) STORED,
  "identifier" text
    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{identifier}') = 'string' THEN (doc #>> '{identifier}') END) STORED,

  -- Scoped to the tenant rather than global: two tenants restored from
  -- different deployments can legitimately carry the same _id, and a
  -- global unique constraint would make one of them unimportable.
  PRIMARY KEY (tenant_id, "_id")
);

CREATE INDEX treatments_tenant_created_at
  ON treatments (tenant_id, "created_at" ASC);
CREATE INDEX treatments_tenant_eventtype
  ON treatments (tenant_id, "eventType" ASC);
CREATE INDEX treatments_tenant_insulin
  ON treatments (tenant_id, "insulin" ASC);
CREATE INDEX treatments_tenant_carbs
  ON treatments (tenant_id, "carbs" ASC);
CREATE INDEX treatments_tenant_glucose
  ON treatments (tenant_id, "glucose" ASC);
CREATE INDEX treatments_tenant_enteredby
  ON treatments (tenant_id, "enteredBy" ASC);
CREATE INDEX treatments_tenant_notes
  ON treatments (tenant_id, "notes" ASC);
CREATE INDEX treatments_tenant_nsclient_id
  ON treatments (tenant_id, (doc #>> '{NSCLIENT_ID}') ASC);
CREATE INDEX treatments_tenant_percent
  ON treatments (tenant_id, "percent" ASC);
CREATE INDEX treatments_tenant_absolute
  ON treatments (tenant_id, "absolute" ASC);
CREATE INDEX treatments_tenant_duration
  ON treatments (tenant_id, "duration" ASC);
CREATE INDEX treatments_tenant_identifier
  ON treatments (tenant_id, "identifier" ASC);
CREATE INDEX treatments_tenant_eventtype_duration_created_at
  ON treatments (tenant_id, "eventType" ASC, "duration" ASC, "created_at" ASC);
CREATE INDEX treatments_tenant_eventtype_created_at_identifier_date
  ON treatments (tenant_id, "eventType" ASC, "created_at" DESC, "identifier" DESC, (doc #>> '{date}') DESC);

-- FORCE is the load-bearing word: without it the table OWNER bypasses the
-- policy. It still does not subject a SUPERUSER — BYPASSRLS is implicit for
-- one — so anything verifying isolation must connect as a role that is
-- NOSUPERUSER NOBYPASSRLS, or it has verified nothing.
ALTER TABLE treatments ENABLE ROW LEVEL SECURITY;
ALTER TABLE treatments FORCE ROW LEVEL SECURITY;

-- NULLIF so that an unbound connection yields NULL rather than an empty
-- string, and `tenant_id = NULL` is never true: the fail-closed property
-- D3 is chosen for. WITH CHECK is what extends it to writes, which is the
-- axis MongoDB's role-keyed views cannot cover at all ({M} §6.7).
CREATE POLICY treatments_tenant_isolation ON treatments
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
