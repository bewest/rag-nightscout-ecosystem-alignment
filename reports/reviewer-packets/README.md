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
| [`BFQ-185`](bfq-185-ci-edge-diagonal-matrix.md) | #8843 | `in-flight-upstream` | BF-185 - the stress test tier leaves devicestatus documents that break api3.search in a later run |
| [`BFQ-192`](bfq-192.md) | #8843 | `in-flight-upstream` | BF-192 - the populated reports browser test measured a drawn report against an empty-form heap ceiling (test-measurement blind spot, not a product regression) |
| [`RT-CI-DIAGONAL`](rt-ci-diagonal-ci-edge-diagonal-matrix.md) | #8843 | `in-flight-upstream` | CI runs the Node x MongoDB diagonal, the no-database tiers on their own, a Tests pass check and seeded test-file order |
| [`BFQ-179`](bfq-179-chore-compose-mongodb6.md) | #8844 | `in-flight-upstream` | BF-179 - postinstall runs webpack, now a devDependency, so a production install of dev fails (dev b29f1bf7, cut 2) |
| [`BFQ-182`](bfq-182-chore-compose-mongodb6.md) | #8844 | `in-flight-upstream` | BF-182 - on cut 3 (driver 7), boot against MongoDB 4.2 or older retries forever with no HTTP server |
| [`BFQ-145`](bfq-145-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-145 - API v3 PATCH and PUT by the shown id miss a record whose identifier is null, "" or 0 |
| [`BFQ-152`](bfq-152-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-152 - API v3 settings are admin-only through search and history, readable by identifier with read permission |
| [`BFQ-165`](bfq-165-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-165 - a treatment re-send matched by its fallback key is answered without _id |
| [`BFQ-166`](bfq-166-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-166 - a profile re-sent with its own _id answers 500 |
| [`BFQ-167`](bfq-167-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-167 - devicestatus remove()'s filter is not pinned by any test |
| [`BFQ-169`](bfq-169-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-169 - API v3's swagger says clients must not supply identifier, but the server keeps a client-supplied one |
| [`BFQ-170`](bfq-170-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-170 - API v3 stores a client's 24-hex body _id as a string, in the case sent |
| [`BFQ-186`](bfq-186-bf-16-0-0-record-identity.md) | #8845 | `in-flight-upstream` | BF-186 - API v3 logs a whole record when a client's identifier differs from the computed one |
| [`ADV-XSS-META`](adv-xss-meta.md) | &mdash; | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| [`BFQ-161`](bfq-161-bf-entries-pattern-limit.md) | &mdash; | `in-flight-upstream` | BF-161 - braces 3.0.3 (direct dependency) is inside a stack-exhaustion advisory with no fixed release, reachable from the entries pattern routes |
| [`BFQ-72`](bfq-72-bf-regex-limits.md) | &mdash; | `in-flight-upstream` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| [`BFQ-95`](bfq-95.md) | &mdash; | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm |
| [`DEPENDABOT-CONFIG`](dependabot-config.md) | &mdash; | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts count fixes that are on dev |
| [`ID-ABSENT-DECISION`](id-absent-decision.md) | &mdash; | `needs-decision` | Decide: a write that carries no identifier (and no _id) - keep the time-key fallback, deprecate it, or require identifier? |
| [`ID-CLIENT-OID-DECISION`](id-client-oid-decision.md) | &mdash; | `needs-decision` | Decide: may a client set _id (an ObjectId it creates), and which field wins when identifier and _id match different records? |
| [`ID-DELETE-REUSE-DECISION`](id-delete-reuse-decision.md) | &mdash; | `needs-decision` | Decide: after a delete, what does a re-send of the same identifier (or _id) do - resurrect, refuse, or create new? |
| [`ID-FORMAT-DECISION`](id-format-decision.md) | &mdash; | `needs-decision` | Decide: the client identifier's format (opaque string with limits; UUID not required) |
| [`ID-SCOPE-DECISION`](id-scope-decision.md) | &mdash; | `needs-decision` | Decide: is identifier unique per collection, across collections, and per tenant under TENANCY_MODE=multi? |
| [`ID-V3-IMMUTABLE-DECISION`](id-v3-immutable-decision.md) | &mdash; | `needs-decision` | Decide: on an identifier match, may date, device or eventType change? |
| [`MOD-UNITS-CANONICAL`](mod-units-canonical.md) | &mdash; | `needs-decision` | Canonical units at write: spelling only (N1) or mg/dL plus the original (N2), and the conversion constant |
| [`MOD-WRITE-VALIDATION`](mod-write-validation-feat-api3-domain-validation.md) | &mdash; | `ready-to-push` | WRITE_VALIDATION=off|log|reject: opt-in domain validation of Temporary Target writes on API v1 and v3 (draft) |
| [`MOD-WRITE-VALIDATION-READ`](mod-write-validation-read.md) | &mdash; | `needs-decision` | Flag stored records that break a write-validation rule on API v3 reads (read-side flag, R1/R2) |
| [`P0-C-REMEDIATE`](p0-c-remediate.md) | &mdash; | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling |
| [`T30-AUTH`](t30-auth-main.md) | &mdash; | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-interface split |
| [`T30-RESEARCH`](t30-research.md) | &mdash; | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface |
| [`WS-LAB`](ws-lab-main.md) | &mdash; | `ready-to-push` | tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3) |

*Generated by `tools/queue/emit_packets.py` (`make packets`) from `queue/work-queue.yaml`, `measured_at` 2026-09-27.*
