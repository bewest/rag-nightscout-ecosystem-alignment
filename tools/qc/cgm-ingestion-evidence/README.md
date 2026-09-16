# CGM ingestion retirement — preserved evidence harnesses

**Why this directory exists.** These are the harnesses that produced the *reproduced* findings
behind the decision to retire the legacy Dexcom bridge and MiniMed CareLink ingestion paths
(modernization parcel 4). They were written into a session scratchpad under `/tmp` and would have
been lost. A completeness critic flagged that on 2026-09-15: **the evidence for deleting a CGM
ingestion path was not durable.** Preserved here on 2026-09-16.

This matters because of a rule this programme earned the hard way: every backfix-register claim that
had to be retracted was derived from *reading* source, and not one that began with a *reproduction*
has been. These files are the reproductions. Without them, the findings below revert to
read-derived — which is the evidential class that keeps being wrong.

## Provenance and status

- Copied verbatim from the session scratchpad; **not yet reviewed, tidied, or wired into any
  runner.** Treat them as raw evidence, not as maintained QC harnesses.
- Some are one-shot probes with hard-coded paths into `externals/work/*` worktrees and will not run
  unchanged. Promoting the load-bearing ones into real harnesses beside the existing
  `tools/qc/*-arm.js` files is outstanding work.
- **No vendor endpoint was contacted and no real account or credential was used** in producing any
  of these. Fixtures are synthetic throughout; the one credential-looking string is
  `synthetic-account` / `synthetic-password`, and the one database URL reads `PGPASSWORD` from the
  environment against `127.0.0.1`.

## What these back

Findings reproduced with these harnesses, from
[e1-dexcom-path-comparison](../../../docs/60-research/e1-dexcom-path-comparison-2026-09-15.md) and
[e2-medtronic-path-comparison](../../../docs/60-research/e2-medtronic-path-comparison-2026-09-15.md):

| area | finding |
|---|---|
| Dexcom request volume | legacy 72 requests/hour (24 auth + 24 login + 24 glucose) vs connect 16; legacy never reuses a session |
| Dexcom crash | legacy dies on an uncaught `TypeError: glucose.map is not a function` for a non-array body with status < 400; no `uncaughtException` handler exists |
| Dexcom session recovery | on a server-invalidated session **connect is worse** — the session machine is never told, so a dead token persists up to 24 h; legacy recovers on the next poll |
| Dexcom regions | `BRIDGE_SERVER=US` migrates to `shareServer:"US"` → `https://US`, unresolvable, while `validate()` returns `ok:true` |
| Dexcom fidelity | entry records identical except `device`; the `{sysTime, type}` upsert key means cutover cannot duplicate history |
| MiniMed sentinels | the pins operators can reach today ingest CareLink gap sentinels as `sgv 0`, and a leading `0` makes `simplealarms.js` skip the whole high/low evaluation |
| MiniMed clock | with a zone-less payload and a pump east of the server clock, **connect** files the reading in the future and silences both stale-data alarm paths; legacy files it correctly |
| MiniMed crash | `transformPayload` calls `data.markers.filter(...)` unguarded; the retired package's own recorded payloads have no `markers` key, and the synchronous throw kills the process |
| MiniMed follower accounts | care-partner (follower) accounts cannot work through the legacy path at all — `getOptions` never plumbs `patientId` |
| BF-44 | substance and all three published corrections independently reproduced, including whole-hour rounding turning UTC+5:30 into a 6 h divergence |

## Before relying on any of this

Several conclusions remain **unsettleable without a real vendor account**, and they are named in
both research reports. The most consequential: whether real CareLink payloads carry zone designators
on `sgs[].datetime` / `markers[].dateTime` / `sMedicalDeviceTime`. That single property decides
whether the future-dated readings are latent or active — the difference between the retirement
fixing the stale-data-alarm hazard and causing it. Its failure mode is a person's glucose data
quietly stopping without an alarm.

Draft evidence supporting a release decision; requires review by a qualified maintainer before it is
relied upon.
