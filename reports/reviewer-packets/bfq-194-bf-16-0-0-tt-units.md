<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — BFQ-194

**BF-194 - API v1 drops the units of a temp target with no glucose value, so
mmol/L targets read as mg/dL**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-tt-units` |
| base | `official/dev@ca1652d6` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-194` is the measurement |
| semver | `minor` |
| register entries | `BF-194` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

1 commit (7b74110c), 11 files, +742/-43: new lib/treatmentTargetUnits.js (122
lines), called from lib/server/treatments.js prepareData, API v3
create/insert.js, update/replace.js and patch/operation.js, and the socket's
dbAdd and dbUpdate (lib/server/websocket.js); the treatments schema doc; three
test files. The bug itself: prepareData's delete of units together with
glucose and glucoseType when no glucose is given (:639-643 on dev 47723cda,
:566-570 on v15.0.9).

## Why that semver

changes what is stored for a write clients already send

## What an operator would notice

> If an app sends Nightscout a temporary target in mmol/L through the older
> API (v1), Nightscout throws away the units and keeps the numbers, so a
> target of 6.0 mmol/L is stored as 6 and read as 6 mg/dL. Nothing tells
> you. Check a temporary target on your Nightscout page after setting it
> from an app, and talk to your care team about how you set targets.

## Who should review this, and why

maintainer

## What was measured

**`cd externals/work/crm-tt-units && node bin/with-env.js ./my.test.env node_modules/mocha/bin/mocha.js --timeout`** &nbsp;·&nbsp; kind: `integration`

A Temporary Target is stored in mg/dL labelled mg/dl on every write path: API
v1 POST (one and a batch) and PUT, in-process create and save, API v3 POST,
PUT and PATCH, socket dbAdd (one and an array) and dbUpdate; other event types
and untouched stored records are left alone. Control 2026-10-27: the same test
files over dev ca1652d6's lib/ fail 45 of 499 (with the write-validation and
CRUD matrix files), every failure a stored value or label left unconverted,
none a missing module. Needs the worktree's untracked my.test.env (MongoDB on
127.0.0.1:27195).

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/remedial/rc-16.0.0-integration-record.md`](../../docs/30-design/remedial/rc-16.0.0-integration-record.md)

## Notes carried on the item

2026-10-27 evening, verified by session -4f on 7b74110c (rebased on dev
ca1652d6; d4435f18 was the same commit before an amend that updated
tests/api.crud-by-id.matrix.test.js only): red control as in the gate; npm
test 4750 passing, 0 failing, 3 pending; test:all exit 0 (all seven tiers;
Node v22.23.4, MongoDB 7.0). Write paths checked by reading: every v1 entry
(create, createChecked, upsert, save) goes through prepareData; dbUpdateUnset
only removes fields and cannot introduce mmol numbers; the helper is
idempotent, so a socket dbAdd that is converted and then prepared again is
unchanged. The rule matches the read side: ddata converts both targets when
either is below 20, and so does the helper. Label spelling: the code writes
mg/dl, not the mg/dL of the decision text. mg/dl is write-validation's
canonicalUnits, ddata's and the careportal's spelling, and the exact text of
AAPS's GlucoseUnit.MGDL (fromText matches exactly, falling back to mg/dL); the
survey's other label readers accept it (the reporter case-insensitive,
nightguard checks for mol). Not done: a mixed patch (units mmol with one
target in mmol and the stored other above 30) keeps the numbers as sent, an
edge no surveyed client sends. 2026-10-27: building on local bf/16.0.0-tt-
units (worktree externals/work/crm-tt-units, off dev 7abe1cf6; session -ee's
agent). Rule as briefed: a target labelled mmol (any spelling) is converted
with the careportal's arithmetic; an unlabelled target below 20 is converted
too (the read-side rule of lib/data/ddata.js:486-488, #3549, moved to write,
so Trio's unlabelled-mmol edge case is not stamped mg/dL); every Temporary
Target is then labelled mg/dL; other eventTypes and stored records unchanged.
Decided 2026-10-27 (maintainer), for 16.0.0: convert and always label. At
write, on API v1 and v3, a Temporary Target labelled mmol is converted to
mg/dL, and every Temporary Target is stored with units mg/dL (the spelling
every surveyed label-honouring reader accepts). The conversion runs before
v1's units deletion. Fixes BF-194 and nightscout- reporter's misreading of
unlabelled mg/dL targets on mmol sites; changes no surveyed client's numbers.
A release-note line in 16.0.0. 2026-10-27, survey done (session -ee's agent,
read from source; AAPS 7e1d537d, Trio 0b29cd53, iAPS 642a82cd, oref0 d219baf9,
nightguard 75404bd, LoopFollow 4a74b781, xDrip 1ed76004, nightscout-reporter
518d61f): no surveyed client uploads a Temporary Target labelled mmol. AAPS
(API v3) and nightguard send mg/dL labelled mg/dl; Trio and iAPS send mg/dL
with no label (v1); Nightscout's careportal converts first; Loop,
NightscoutKit, LoopCaregiver, DiaBLE and xDrip+ send none. Readers that ignore
the label: Trio, iAPS, oref0, LoopFollow. Read-back by value: none (AAPS
matches by identifier and never compares targets). So BF-194's exposure is
clients outside the survey (scripts, third-party apps). Convert-at-write
changes no surveyed client's records; it must run before v1's units delete,
and relabel as mg/dL (AAPS treats any label but 'mmol' as mg/dL; the reporter
compares mg/dl case- insensitively; nightguard checks for 'mol'). Separate
finding: nightscout-reporter reads an unlabelled target in the site's units,
so unlabelled mg/dL targets (Trio, iAPS, careportal via v1) show wrong on mmol
sites; writing an mg/dL label on every Temporary Target would fix that.
Decision pending. 2026-10-27 (maintainer): survey the clients first (which
apps send or read temp targets in mmol/L, over which API, and whether they
read back their own), then likely enforce mg/dL at write: a target labelled
mmol is converted to mg/dL and relabelled, so readers that ignore the label
(Trio) read it right and Nightscout's read-side conversion
(lib/data/ddata.js:476-488, #3549 in 2018) does not convert it twice. History:
the units deletion dates from a6182b55 (2015-02-11, 'if there isn't a glucose
value, don't store the units'), before temp targets carried units; #3549
(2018) added the read-side mg/dL normalisation, which a v1-written target's
missing label defeats only for readers outside Nightscout's own page. Survey
running (session -ee). Filed 2026-10-26 from R15. Needs a maintainer decision:
keep units on a record with targets when no glucose is given, convert to
mg/dL, or refuse under WRITE_VALIDATION=reject. Related to BF-180 (the
careportal path through the same lines, merged in #8842) and MOD-UNITS-
CANONICAL.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-194` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
