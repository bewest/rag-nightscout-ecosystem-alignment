# Acceptance campaign on the M6b joined candidate `3545236d`: stopped on a join defect

*Contributor-facing measurement record, captured 2026-11-10. Not edited after capture.*

Candidate: `externals/work/crm-m6b-join-20261110`, branch `codex/m6b-join-20261110`, head
`3545236d0c8f298d90d192591c78765ad65f63b3`, clean tree (confirmed before the run and after the
temporary repair evaluation). Baseline: `dc795bd1` (`reports/tenancy/m6a-join-2026-11-09/dc795bd1-acceptance/`).

Environment: `my.test.env` (git-ignored, removed afterwards) = `tests/ci.test.env` with
`CUSTOMCONNSTR_mongo` on a dedicated container `ns-acc-mongo`, image `mongo:7`
(`mongo@sha256:9854f7139445d766a9523571d6f047530c45547460ffcf8259eb2bf4264632ca`), server 7.0.43,
`--ulimit nofile=1048576:1048576`, no tmpfs, 127.0.0.1:27717. Container removed afterwards.
Bundle: `npm run bundle` (production), exit 0.

## Results (2026-11-10T20:04:13Z – 20:11:38Z)

| suite | files | passing | pending | failing | baseline `dc795bd1` |
|---|---|---|---|---|---|
| unit | 234 | 3106 | 0 | 0 | 3072 |
| dom | 19 | 205 | 0 | 0 | 205 |
| dependency | 32 | 368 | 2 | 0 | 368 / 2 |
| core | 26 | 319 | 0 | 0 | 319 |
| harness | 10 | 99 | 0 | 0 | 99 |
| integration | 250 | 3624 | 547 | **2** | 3618 / 534 |
| stress | 1 | 18 | 0 | 0 | 18 |
| `test:all` exit | | | | 2 | 0 |
| browser | 42 | 686 | 0 | 0 | 686 |

Raw: `test-all-and-browser.log`; summary `test-all-and-browser.txt`.

## Failure and diagnosis (reproduced): join defect in `3545236d`

Both failures are hooks of `tests/human-session-provision.test.js` (`TypeError: Cannot read
properties of undefined (reading 'collection')` at :43, i.e. `ctx.store` undefined).

Mechanism: `lib/server/env.js:166` deletes `API_SECRET` from `process.env` once read. The tier runs
files in one mocha process in sorted order; `tests/headless-test-server.test.js` (immediately before
it) reads env first, so the provision file's `before()` builds an env with no `API_SECRET`, boot
stops after `checkEnv` (log shows no "Setting up new connection to MongoDB"), and `ctx.store` is
never set. The lane ran the file alone, where it is the first reader. `3545236d` registered the file
in the integration tier and so exposed it.

`provision-order-diagnosis.txt`:

- file alone: 24 passing;
- `headless-test-server` + provision (tier order): 11 passing, 2 failing, same TypeError;
- proposed repair (temporary, restored, tree clean afterwards): set `process.env.API_SECRET` to a
  fresh random value at the top of the `before()`, as `tests/headless-test-server.test.js:110-112`
  does. Pair: 30 passing, 0 failing. Full integration tier: **3643 passing, 547 pending, 0 failing**,
  exit 0 (`integration-with-proposed-repair.log`/`.txt`).

## Not run (campaign stopped per brief at the first join defect)

Multitenant corpus, OIDC nine-stage matrix + controls + `oidc-native-recorded` gate, `test:tiers`,
write-intent/write-boundary, `npm run lint`, prcheck, and the lane native instruments
(key-retention, ownership PostgreSQL/HTTP family, internal-api-compose + `blanket-window` control).
All UNMEASURED on this candidate.
