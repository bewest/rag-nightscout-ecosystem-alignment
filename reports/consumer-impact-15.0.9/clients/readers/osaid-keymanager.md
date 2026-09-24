# osaid-keymanager — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/osaid-keymanager (Flask service + cron job + Terraform: an App-Attest /
  key-issuing backend for Trio/Loop builds).
- Ref analysed: `origin/main` **e9c3b73 (2026-07-07)**; local HEAD = e9c3b73, behind 0, dirty 0.
  `origin/dev` is the same commit (e9c3b73).
- All claims **read-derived**.

## Verdict: does not talk to Nightscout

**Positive control (the search reaches this repo's network code):**
`git grep -n -E "^\s*(import|from) (requests|httpx|aiohttp|urllib|http\.client|boto3|flask)" origin/main`
finds its I/O: inbound Flask routes (`app/o5/routes.py:8`, `app/routes_status.py:18` `/api/status/ios`),
object storage (`app/o5/storage.py:11` boto3), and **one** outbound HTTP client, `app/logs.py:18`
(`requests`), which posts log batches to a configured Loki URL (`app/logs.py:52-97`,
`terraform/observability.md:19-20`).

**Absence searches (all no hit in `app/`, `cronjob/`):** `api/v1/`, `api/v3/`, `entries.json`,
`treatments.json`, `devicestatus`, `api-secret`, `X-Forwarded`, `token=`, `socket`.
The only "nightscout" strings are bundle-id patterns (`org.nightscout.<team>.trio`) used to
classify callers (`app/o5/routes.py:33,123`); `/api/v1/push` appears only as Scaleway Cockpit
endpoints in Terraform (`terraform/environments/prod/variables.tf:61`).

| S-id | finding | patterns |
|---|---|---|
| S1–S15 | none: no Nightscout request of any kind | as above |

**Impact: none.**
