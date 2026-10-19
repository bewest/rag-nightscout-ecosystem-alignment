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

# Review packet — ID-FORMAT-DECISION

**Decide: the client identifier's format (opaque string with limits; UUID not
required)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@fade2299` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ID-FORMAT-DECISION` is the measurement |
| semver | `n/a` |

## What this changes

A decision row, no code. Its answer sets ID-VALIDATE's limits and
ID-V1-LOOKUP's matching, and is published in the API description.

## Why that semver

a decision; the code that follows is classed in ID-VALIDATE and ID-V1-LOOKUP

## Who should review this, and why

maintainer, after the Loop maintainers answer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision, not measurable. Proposed answer (research note identifier-
  format-2026-10-17 §6.2, reply rewritten 2026-10-17): an opaque, case-
  sensitive string, 1 to 256 characters from [A-Za-z0-9._~:-], not exactly
  24 hex, not history, ., .., invalid, undefined, null or NaN; one
  identifier names one record per collection. UUID not required: v4 for a
  one-device record, v5 of a scheme-prefixed source-derived name (in a
  published Nightscout client namespace) when several devices must agree,
  needed only by clients that use the v1 by-_id routes. Open: the 256 limit,
  the character set (Loop's current CGM keys contain spaces; 503 Loop
  syncIdentifiers at one corpus site contain /), and the client namespace.

## Blocked on

`LOOP-ID-REPLY`

## Evidence

- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)
- [`docs/60-research/tenancy/identifier-duplicates-2026-10-17.md`](../../docs/60-research/tenancy/identifier-duplicates-2026-10-17.md)
- [`docs/60-research/tenancy/identifier-format-2026-10-17.md`](../../docs/60-research/tenancy/identifier-format-2026-10-17.md)

## Notes carried on the item

Today: v1 recognises only UUID-shaped values as identifiers in by-id routes
(UUID_RE, case-insensitive, lib/server/query.js:12 at dev fade2299), while
stored identifiers are compared exactly, so Loop's upper-case override UUIDs
match only themselves. API v3 computes uuid.v5(device_date[_eventType],
"NightscoutRocks!") when none is sent (lib/api3/shared/operationTools.js:6,
106). A random UUID cannot serve the phone-and-watch case, where both devices
must derive the same value; AndroidAPS keys on pump event ids. Not required:
changing an existing client's identifiers, which would break matching against
records it already stored. 2026-10-17: the rewritten Loop reply states only "a
string, UUID recommended" and lists the limit, character set and case under
"later, only if needed"; decide when a client or ID-VALIDATE needs it.
Maintainer, 2026-10-18 (decided): identifier is opaque to the server and
follows one rule in every collection, plus a published conventions table per
record kind so apps converge on one value (docs/30-design/platform/identifier-
conventions.md, ID-CONVENTIONS). URL syntax: <scheme>://<segment>/<segment>.
Things that exist outside the app (sensor readings, pump events) use a source
scheme with the manufacturer as the scheme and the model as the first segment
(dexcom://g7/<serial>/<offset>, dexcom://g6/<transmitterId>/<time>,
abbott://libre3/<serial>/<lifeCount>); things created in an app (manual carbs,
boluses, overrides, temporary targets) use an app scheme
(loop://carbs/<uuid>). A controller may use one format of its own across
collections (loop://carbs/<uuid>, loop://tempbasal/<syncId>,
loop://override/<uuid>, loop://devicestatus/<uuid>): unique per collection,
within the limits, stable across re-sends; a registered instance declares it.
The kind segment separates the measured Loop Suspend Pump + Temp Basal pairs
that share one syncIdentifier (identifier-duplicates §2.2: 9 of the 13 shared
values). The '/' question, measured 2026-10-18 (identifier-format §3.4, url-
identifier-probes.js; 15.0.8 92d08342 and dev fade2299, mongo:7 7.0.43, no
proxy, same result at both): a URL-form identifier is stored exactly; percent-
encoded as one path segment (%3A, %2F) it works on v3 GET, PATCH, PUT, PUT-
create and DELETE; raw '/' in the path is 404; v3 ?identifier$eq= and v1
find[identifier]= find it; v1 DELETE by it deletes nothing (UUID_RE). So C3
becomes [A-Za-z0-9._~:/-] and clients must percent-encode the identifier in v3
paths. Still open: the 256 limit and the rest of C1-C8 as written in the
conventions page §2, reverse proxies and %2F (not measured), the UUIDv5 client
namespace, and whether the client developers accept the templates.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-FORMAT-DECISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
