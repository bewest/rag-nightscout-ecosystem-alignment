-- 0001: the seam's platform tables, VERBATIM from cgm-remote-monitor 81a1f6ce:lib/admin/platform.sql.
-- Kept byte-identical below this header so the config migrations are shown to extend it
-- without altering it (tools/lab/tenant-config-schema/README.md, 'Compatibility').

-- The platform tables: the map of tenants, and who may act inside one.
--
-- Hand-written, unlike lib/storage/postgres/generated/*.sql. Those are emitted
-- from specs/nsschema because they hold Nightscout DOCUMENTS and the document
-- shapes have a source of truth. These two hold the deployment's own
-- bookkeeping, have no document behind them, and are adapted from Nocturne's
-- TenantEntity / TenantMemberEntity, which are already in production shape.
--
-- bin/admin.js is the ONLY writer of `tenants`. Everything else in the system
-- reads it: tenant resolution turns a Host header into a slug and a slug into
-- the uuid that every RLS policy compares against. That asymmetry is the whole
-- design -- one writer, on a port that is not routed -- and it is why the write
-- path can afford to be this fussy.

-- `tenants` is DELIBERATELY NOT RLS-PROTECTED.
--
-- Not an oversight and not a TODO. This is the table read to DECIDE which
-- tenant a request belongs to, which necessarily happens before a tenant
-- context exists; a policy comparing app.current_tenant_id would return zero
-- rows on every lookup and the deployment would resolve nothing. The protection
-- this table gets is that only one component writes it and that component is
-- unreachable.
CREATE TABLE tenants (
  id              uuid PRIMARY KEY,
  -- A HOST LABEL, never a host (D10). `foo`, not `foo.example.org`: the
  -- deployment's resolver owns the rule that maps a Host header to this label,
  -- so a hoster who moves from foo.a.org to foo-a.org rewrites a config line
  -- and not a single row here.
  --
  -- The CHECK is an addition to the plan's §2.4, which specifies the charset as
  -- a rule bin/admin.js enforces. It is enforced in both places on purpose:
  -- this component is cross-tenant by construction and cannot be protected by
  -- RLS, so its correctness rests on code review, and a constraint the database
  -- holds is the one piece of that which does not. It constrains writes only --
  -- a reader of this table is unaffected by it.
  slug            text NOT NULL UNIQUE
                  CHECK (slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$' AND length(slug) <= 63),
  display_name    text NOT NULL DEFAULT '',
  -- Suspension is a state, not a deletion. An inactive tenant answers 403 and
  -- not 404: "your site is switched off" and "your site never existed" are
  -- different sentences to say to someone whose glucose data is behind it.
  is_active       boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now(),
  -- Signal-loss detection. The INGEST path updates this; the admin plane only
  -- ever reads it, which is why there is no endpoint here that sets it.
  last_reading_at timestamptz
);

CREATE TABLE tenant_members (
  id            uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  subject_id    uuid NOT NULL,
  permissions   text[],            -- shiro strings, as today's auth_subjects carries
  label         text,
  last_used_at  timestamptz,
  UNIQUE (tenant_id, subject_id)
);

-- `tenant_members` IS RLS-protected, and for the opposite reason to `tenants`:
-- it is read INSIDE a tenant context, by the tenant's own admin plane, which is
-- an ordinary authenticated consumer request. The policy is character-for-
-- character the one the emitted document tables carry, because a second spelling
-- of the same predicate is a second thing that can drift.
ALTER TABLE tenant_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_members FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_members_tenant_isolation ON tenant_members
  USING      (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- OPERATIONAL NOTE, not something this file can do for you: the role that runs
-- bin/admin.js owns these tables. If the application connects as a DIFFERENT
-- role -- which is the shape a careful hoster will want, since the admin role
-- is the one that can delete tenants -- that role needs `GRANT SELECT ON
-- tenants` before resolution will work, and `GRANT SELECT, INSERT, UPDATE,
-- DELETE ON tenant_members`. There is no endpoint here that issues those
-- grants; handing the admin plane the ability to widen access to itself would
-- undo the reason it is on its own port.
