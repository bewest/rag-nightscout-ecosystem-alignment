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

# Reviewer packets

One bounded packet per item whose next move is a human review or decision.
Each says what changed, what was measured, and - the section worth opening
first - what the measurement does not cover. Start at
docs/00-overview/REVIEWER-ONBOARDING.md if this is your first time in this
repository.

| packet | PR | claimed state | what it is |
|---|---|---|---|
| [`ADV-CONFIG`](adv-config.md) | #8746 | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-77, BF-78, BF-81) |
| [`BFQ-ENV`](bfq-env-bf-16-0-0-boot-resilience.md) | #8849 | `needs-decision` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| [`PLAT-ENTRY`](plat-entry-feat-nightscout-entrypoint.md) | #8862 | `in-flight-upstream` | One executable (D21): bin/nightscout.js with `single` and the operator tools; image ENTRYPOINT and CMD single, no image HEALTHCHECK; no start path changes |
| [`BFQ-212`](bfq-212-bf-16-0-0-split-identity.md) | #8878 | `in-flight-upstream` | BF-212 - a chart-drag split leaves two treatments with one client identity; a re-send can overwrite one's amount, and a re-upload can show the moved insulin twice |
| [`ID-FIRST-MATCH`](id-first-match-feat-id-first-match.md) | #8879 | `in-flight-upstream` | Identifier-first matching on every collection and path, with D-LOOP-ID's rules (eligible for 16.0.0 through the entry bar) |
| [`DEV-LINT-OVERLAY-REGEX`](dev-lint-overlay-regex-hygiene-dev-lint-overlay.md) | #8882 | `in-flight-upstream` | Development builds show a lint-warning popup on every page: lib/profilefunctions.js:251's anchored GMT/UTC offset regex trips security/detect-unsafe-regex (false positive) |
| [`UI-DRAWER-RESIZE`](ui-drawer-resize-hygiene-dev-lint-overlay.md) | #8882 | `in-flight-upstream` | A drawer opened in a narrow window keeps its narrow size when the window grows (inline pixel sizes set once in openDrawer) |
| [`BFQ-219`](bfq-219-bf-16-0-0-batch-replies.md) | #8883 | `in-flight-upstream` | BF-219 - a v1 treatments batch with a preBolus answers with more items than were sent |
| [`BFQ-220`](bfq-220-bf-16-0-0-batch-replies.md) | #8883 | `in-flight-upstream` | BF-220 - a duplicate _id inside a v1 batch answers 5xx after the items before it are stored |
| [`BFQ-221`](bfq-221-bf-16-0-0-batch-replies.md) | #8883 | `in-flight-upstream` | BF-221 - a v1 treatment PUT reaches open pages up to about a minute late |
| [`BFQ-222`](bfq-222-bf-16-0-0-batch-replies.md) | #8883 | `in-flight-upstream` | BF-222 - API v3 autoPrune can leave pruned records in the server's cache |
| [`ADV-XSS-META`](adv-xss-meta.md) | &mdash; | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| [`BFQ-161`](bfq-161-adv-phrf-1600-dev.md) | &mdash; | `in-flight-upstream` | BF-161 - braces 3.0.3 (direct dependency) is inside a stack-exhaustion advisory with no fixed release, reachable from the entries pattern routes |
| [`BFQ-72`](bfq-72-adv-r3gv-1600-dev.md) | &mdash; | `in-flight-upstream` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| [`BFQ-95`](bfq-95.md) | &mdash; | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm |
| [`DEPENDABOT-CONFIG`](dependabot-config.md) | &mdash; | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts count fixes that are on dev |
| [`LOOP-UPSTREAM-CARB-EDIT`](loop-upstream-carb-edit.md) | &mdash; | `in-flight-upstream` | Loop 3.14.9 drops a carb edit when the record's _id is no longer in its 24 h cache (raised with the Loop maintainers) |
| [`MOD-UNITS-CANONICAL`](mod-units-canonical.md) | &mdash; | `needs-decision` | Canonical units at write: spelling only (N1) or mg/dL plus the original (N2), and the conversion constant |
| [`MOD-WRITE-VALIDATION-READ`](mod-write-validation-read.md) | &mdash; | `needs-decision` | Flag stored records that break a write-validation rule on API v3 reads (read-side flag, R1/R2) |
| [`P0-C-REMEDIATE`](p0-c-remediate.md) | &mdash; | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling |
| [`T30-AUTH`](t30-auth-main.md) | &mdash; | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-interface split |
| [`T30-RESEARCH`](t30-research.md) | &mdash; | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface |
| [`WS-LAB`](ws-lab-main.md) | &mdash; | `ready-to-push` | tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3) |

*Generated by `tools/queue/emit_packets.py` (`make packets`) from `queue/work-queue.yaml`, `measured_at` 2026-09-27.*
