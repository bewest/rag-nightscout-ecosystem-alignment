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

# Review packet — BFQ-170 (PR #8845)

**BF-170 - API v3 stores a client's 24-hex body _id as a string, in the case
sent**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-170` is the measurement |
| semver | `minor` |
| register entries | `BF-170` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api3/generic/create/operation.js (or the v3 storage insertOne in
lib/api3/storage/mongoCollection/modify.js): what v3 create does with a body
_id. No v1, socket or read-path change.

## Why that semver

Versioning policy section 2, question 10, for option (a): a record written
with an upper-case 24-hex _id comes back from v1 with its _id in lower case, a
differently-shaped body for the same query. Option (b), refusing a body _id
with 400, would instead be question 3 (an accepted input narrowed) and a major
under R1, though no corpus client sends one. The number follows the option the
maintainer picks.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Filed only. Reproduced over HTTP by tools/lab/record-identity
  (results/record-identity-2026-10-18.md), cases "v3 treatments POST: 24-hex
  _id in body, no identifier" and "v3 treatments POST: identifier + 24-hex
  _id in body": stored _id:string=sent on 15.0.8 92d08342 and fade2299. A
  fix's gate is those two cells reading _id:oid=sent (option a) or 400 with
  nothing stored (option b) on the fix build, with fade2299 as the red
  control; the write-contract matrix cells <col> v3 resend-hex and v3
  resend-upper cover the other collections.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/record-identity/results/record-identity-2026-10-18.md`](../../tools/lab/record-identity/results/record-identity-2026-10-18.md)
- [`docs/30-design/tenancy/write-contract-spec-2026-10-07.md`](../../docs/30-design/tenancy/write-contract-spec-2026-10-07.md)

## Notes carried on the item

2026-10-25, later: in PR #8845 to dev (branch bf/16.0.0-record-identity; the
remote shows 539856ef; head bf37858e after merging dev 428b20b7, pending
push). 2026-10-25: decided (maintainer): API v3 rejects a client-supplied _id,
amending identity rule I2 for API v3 only. Fixed on bf/16.0.0-record-identity
(PR #8845, head bf37858e after merging dev 428b20b7, pending push; session
f4's identity lane): 304827fd (create and PUT answer 400) and b899edc1,
rewritten from 108592de (PATCH answers 400 with "Field _id cannot be modified
by the client" instead of 500; maintainer, option 1). External survey (read):
no API v3 client sends _id (AndroidAPS dev and 3.4.2.6, nightscout-librelink-
up bff2317; nightscout-connect has no API v3 output; Nocturne does not write
to Nightscout's API v3). Record-identity lab, reported by the lane: 60 cases,
4 intended differences. Candidate C1 of the write-contract note (section 7),
filed 2026-10-18. On 15.0.8 a v1 find[_id] for the record misses it (query.js
converts to an ObjectId); on dev v1 matches both forms (object-id-forms
matchEitherForm), except an upper-case string asked for in lower case. Both
read, not measured. No corpus client sends _id to v3; the Loop reply's rule 1
says a client ObjectId _id holds over v1 only. Natural vehicle for option (a):
OID-STORAGE-HELPER, one storage-level rule for writes by _id, which would give
v3 create the same toStoredId conversion v1 uses. C2 (a {"$oid": ...} body _id
answers 500 on v3) is the same code path. ID-CLIENT-OID-DECISION's answer (may
a client set _id) bears on whether option (b) is acceptable.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-170` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
