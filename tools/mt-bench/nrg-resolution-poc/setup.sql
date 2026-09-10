-- Shaped after nightscout-roles-gateway's actual resolution query
-- (lib/policies/index.js:33-49, find_expected_name): a two-table LEFT JOIN keyed by
-- hostname, not a single-table primary-key lookup, because NRG separates "the site
-- registration" from "the confirmed-authentic upstream" as two records.
CREATE TABLE registered_sites (
  expected_name text PRIMARY KEY,
  tenant_id uuid NOT NULL,
  upstream_origin text NOT NULL,
  is_enabled boolean NOT NULL DEFAULT true
);
CREATE TABLE nightscout_authenticity_records (
  expected_name text PRIMARY KEY REFERENCES registered_sites(expected_name),
  upstream_origin text,
  status text,
  acceptable boolean NOT NULL DEFAULT true
);

INSERT INTO registered_sites (expected_name, tenant_id, upstream_origin)
SELECT 'site-' || i || '.example.com', gen_random_uuid(), 'http://ns-' || i || '.internal:1337'
FROM generate_series(1, 2000) AS i;

INSERT INTO nightscout_authenticity_records (expected_name, upstream_origin, status, acceptable)
SELECT expected_name, upstream_origin, 'confirmed', true FROM registered_sites;

CREATE ROLE nrg_reader LOGIN PASSWORD 'poc' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT SELECT ON registered_sites, nightscout_authenticity_records TO nrg_reader;
