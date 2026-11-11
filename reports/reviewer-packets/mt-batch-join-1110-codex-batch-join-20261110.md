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

# Review packet — MT-BATCH-JOIN-1110

**Join the 2026-11-10 decision batch (eight lanes) onto #8898 and run full
acceptance**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/batch-join-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-BATCH-JOIN-1110` is the measurement |
| semver | `n/a` |
| register entries | `BF-229`, `BF-230`, `BF-231`, `BF-232` |

## What this changes

Fast-forward of #8898 by 37 commits: internal listener, pause/suspend, export
expiry, admin lifecycle fit (BF-230), root admin parity (BF-229), consumer
revision and repeat clock (BF-231), tenant extended settings (BF-232), and
seven join repairs.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-batch-join-20261110`

Lane unit tests on the joined head 16a1fc2d: 62 passing. Full campaign on
frozen 3cd1c487 and delta campaign on 16a1fc2d (all 0 failing, prcheck OK) in
reports/tenancy/batch-join-2026-11-10/16a1fc2d-acceptance/README.md.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`reports/tenancy/batch-join-2026-11-10/16a1fc2d-acceptance/README.md`](../../reports/tenancy/batch-join-2026-11-10/16a1fc2d-acceptance/README.md)

## Notes carried on the item

2026-11-10: accepted, not pushed. Frozen 3cd1c487: unit 3167, dom 205,
dependency 368/2, core 319, harness 99, integration 3643/593, stress 18,
browser 686, corpus 596/1 (54 suites), OIDC matrix 9/9 with three controls.
Final 16a1fc2d adds BF-232 (environment.js only; production bundle byte-
identical): unit 3176, the other tiers re-run, 18 environment-reaching corpus
suites 160/1. Open follow-ups: activity selections and grants in the demo
config; export-expiry removeArtifact production wiring; API ingest refusal and
socket disconnect under suspend are wired in core but not in the deploy demo.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-BATCH-JOIN-1110` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
