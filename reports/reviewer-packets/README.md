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
| [`BFQ-193`](bfq-193-bf-16-0-0-log-privacy.md) | #8856 | `in-flight-upstream` | BF-193 - the realtime socket and other write paths log every record written through them |
| [`BFQ-195`](bfq-195-bf-16-0-0-null-removes.md) | #8859 | `in-flight-upstream` | BF-195 - a stale profile is pushed over the socket after a profile re-send |
| [`ID-SIMPLE-MATCH`](id-simple-match-bf-16-0-0-null-removes.md) | #8859 | `in-flight-upstream` | API v1 entries and devicestatus match on identifier like treatments (the simple contract) |
| [`ST-FILTER-READS`](st-filter-reads-feat-storage-filter.md) | #8861 | `in-flight-upstream` | Storage interface, first PR: the filter tree and interface methods under API v3's adapter (ST-FILTER), and API v1 reads through them (ST-READS), with no v1 answer changed |
| [`ADV-XSS-META`](adv-xss-meta.md) | &mdash; | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| [`ARCH-8854-FAILED`](arch-8854-failed.md) | &mdash; | `needs-decision` | Decide: the socket's failed slot that #8854 adds under WRITE_VALIDATION=reject - ship as is, or agree it alongside refused (and on API v1?) |
| [`BFQ-161`](bfq-161-bf-entries-pattern-limit.md) | &mdash; | `in-flight-upstream` | BF-161 - braces 3.0.3 (direct dependency) is inside a stack-exhaustion advisory with no fixed release, reachable from the entries pattern routes |
| [`BFQ-194`](bfq-194.md) | &mdash; | `needs-decision` | BF-194 - API v1 drops the units of a temp target with no glucose value, so mmol/L targets read as mg/dL |
| [`BFQ-72`](bfq-72-bf-regex-limits.md) | &mdash; | `in-flight-upstream` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| [`BFQ-95`](bfq-95.md) | &mdash; | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm |
| [`DEPENDABOT-CONFIG`](dependabot-config.md) | &mdash; | `needs-decision` | Dependabot runs with no configuration: security PRs target master, and alerts count fixes that are on dev |
| [`ID-ABSENT-DECISION`](id-absent-decision.md) | &mdash; | `needs-decision` | Decide: a write that carries no identifier (and no _id) - keep the time-key fallback, deprecate it, or require identifier? |
| [`ID-CLIENT-OID-DECISION`](id-client-oid-decision.md) | &mdash; | `needs-decision` | Decide: may a client set _id (an ObjectId it creates) over API v1? (API v3 decided: refused, BF-170) |
| [`ID-DELETE-REUSE-DECISION`](id-delete-reuse-decision.md) | &mdash; | `needs-decision` | Decide: after a delete, what does a re-send of the same identifier (or _id) do - resurrect, refuse, or create new? |
| [`ID-FORMAT-DECISION`](id-format-decision.md) | &mdash; | `needs-decision` | Decide: the client identifier's format (opaque string with limits; UUID not required) |
| [`ID-SCOPE-DECISION`](id-scope-decision.md) | &mdash; | `needs-decision` | Decide: is identifier unique per collection, across collections, and per tenant under TENANCY_MODE=multi? |
| [`ID-V3-IMMUTABLE-DECISION`](id-v3-immutable-decision.md) | &mdash; | `needs-decision` | Decide: on an identifier match, may date, device or eventType change? |
| [`MOD-UNITS-CANONICAL`](mod-units-canonical.md) | &mdash; | `needs-decision` | Canonical units at write: spelling only (N1) or mg/dL plus the original (N2), and the conversion constant |
| [`MOD-WRITE-VALIDATION-READ`](mod-write-validation-read.md) | &mdash; | `needs-decision` | Flag stored records that break a write-validation rule on API v3 reads (read-side flag, R1/R2) |
| [`P0-C-REMEDIATE`](p0-c-remediate.md) | &mdash; | `ready-to-push` | Operator remediation for tokens already stored in plaintext - text, not tooling |
| [`T30-AUTH`](t30-auth-main.md) | &mdash; | `ready-to-push` | The auth plane - Ory Kratos/Hydra against building it ourselves, and the three-interface split |
| [`T30-RESEARCH`](t30-research.md) | &mdash; | `needs-decision` | T3.0 part 1 - enumerate the per-tenant configuration surface |
| [`WS-LAB`](ws-lab-main.md) | &mdash; | `ready-to-push` | tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3) |

*Generated by `tools/queue/emit_packets.py` (`make packets`) from `queue/work-queue.yaml`, `measured_at` 2026-09-27.*
