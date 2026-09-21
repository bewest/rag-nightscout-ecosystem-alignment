# GHSA-mjp4-84fw-gj4v — stored XSS via API v3 treatment notes

**Already fixed in 15.0.8**, root cause *and* sink, verified end to end with a positive v15.0.7
control from the same run. This advisory needs metadata, not a fix.

## Metadata changes

| field | now | change to | why |
|---|---|---|---|
| `vulnerable_version_range` | `<= 15.0.7` | **keep** | confirmed |
| `patched_versions` | **blank** | **`15.0.8`** | a closed vulnerable range with a blank patched field says "fixed in something" and "fixed in nothing" at once |
| `severity` | `high` | **`high`** (keep) | |
| `cvss_vector_string` | *(none)* | **`CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N`** = 8.4 | the advisory's own proposed vector with `UI:P` corrected to `UI:A` |
| (optional 3.1) | — | `CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:N` = 8.7 | for consumers that do not read 4.0 |

## What was verified

Four write paths across three refs, end to end over real HTTP and socket, with the stored
document read back out of mongo, and API v3 driven with a real JWT on all three refs:

| write path | v15.0.7 | v15.0.8 | dev |
|---|---|---|---|
| `POST /api/v1/treatments` | sanitized | sanitized | sanitized |
| `POST /api/v3/treatments` | **payload survives** | sanitized | sanitized |
| `PUT /api/v3/treatments/{id}` | **survives** | sanitized | sanitized |
| `PATCH /api/v3/treatments/{id}` | **survives** | sanitized | sanitized |

The fix is **broader than the advisory claims**: `PUT /api/v1/treatments/`, `POST /api/v1/food`
and `POST /api/v1/activity` also had no purification at 15.0.7 and now do.

The sink is closed too: the day-to-day report's `.html(treatment.notes)` is gone. In a real
headless browser, v15.0.7 executed the payload (`document.title` changed, three live
`img[onerror]`); 15.0.8 and `dev` render it as visible text.

## One sentence to add, and it is the most operationally useful thing here

> **No remediation of stored data is required after upgrading.** A payload written by a 15.0.7
> server does **not** execute on a patched server. Verified by inserting it directly into the
> database, bypassing every write path, and then rendering the affected pages: the day-to-day
> report in a real browser and the dashboard tooltip against each release's own renderer. This
> holds only because the output-escaping half of the fix shipped alongside the input-purification
> half — had only the purifier landed, existing records would still have been dangerous.

Without that sentence every operator who ran 15.0.7 has to wonder whether their database is
still carrying live payloads.

## Also worth noting in the body

State the affected/patched **git tags and image tags**. npm `nightscout` stops at 14.2.11 (2022),
so `<= 15.0.7` matches no published package and `npm audit` will never fire on it.
