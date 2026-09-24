# trio-telemetry — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/trio-telemetry (Flask backend receiving anonymous Trio usage pings, an S3 ETL
  cron job, Terraform).
- Ref analysed: `origin/master` **681ea86 (2026-09-18)**; local HEAD = 681ea86, behind 0, dirty 0.
- All claims **read-derived**.

## Verdict: does not talk to Nightscout

**Positive control:** `git grep -n -E "^\s*(import|from) (requests|httpx|aiohttp|urllib|http\.client|boto3|flask)" origin/master`
finds its I/O: inbound routes (`trio-telemetry-backend/app/main.py:16,65` `/anonymous`,
`app/routes_attest.py:24`), S3 (`app/storage.py:5`, `trio-telemetry-cronjob/ingest/common.py:7`),
and one outbound client, `trio-telemetry-backend/app/logs.py:17` (`requests`, log shipping).

**Absence searches (no hit in `trio-telemetry-backend/app`, `trio-telemetry-cronjob/ingest`):**
`api/v1/`, `api/v3/`, `entries.json`, `treatments.json`, `devicestatus`, `api-secret`,
`X-Forwarded`, `socket`. "nightscout" appears only as a bundle-id pattern
(`app/config.py:36`) and as a ping field `nightscoutPaired` — a boolean the Trio app reports
about itself (`trio-telemetry-cronjob/ingest/etl.py:56,95,208`). `/api/v1/push` is the Cockpit
metrics endpoint (`terraform/modules/cockpit/outputs.tf:33`).

| S-id | finding | patterns |
|---|---|---|
| S1–S15 | none: no Nightscout request of any kind | as above |

**Impact: none.** (It could *measure* uptake: `nightscoutPaired` counts Trio installs paired with
a Nightscout site, but it carries no server version.)
