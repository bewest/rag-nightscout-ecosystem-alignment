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

# Review packet — MOD-UNITS-CANONICAL

**Canonical units at write: spelling only (N1) or mg/dL plus the original (N2),
and the conversion constant**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@b29f1bf7` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=MOD-UNITS-CANONICAL` is the measurement |
| semver | `major` |

## What this changes

N1: units spelling normalised for temp targets under WRITE_VALIDATION (already
in the draft for reject). N2: stored targetTop/targetBottom in mg/dL with the
originals kept; a stored-value change for every client.

## Why that semver

N2 changes stored values; N1 alone, limited to temp targets, would be minor

## What an operator would notice

> Nothing yet. A decision about how Nightscout stores glucose units on
> temporary targets, so that every app reads them the same way.

## Who should review this, and why

maintainer, and the AndroidAPS, Loop (NightscoutKit) and Trio developers

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision item (design D5). The spelling sets differ by client
  (AndroidAPS mmol and mg/dl, NightscoutKit mmol/L and mg/dL, Trio no units
  on temp targets), and the constant differs (18, 18.016, 18.01559). Not
  started.

## Evidence

- [`docs/60-research/modernization/write-validation-design-2026-10-25.md`](../../docs/60-research/modernization/write-validation-design-2026-10-25.md)

## Notes carried on the item

2026-10-26: #8841 merged (e09bca3b): under WRITE_VALIDATION=reject a known
temp-target units spelling is stored as mmol or mg/dl (the PR body), which is
N1 limited to temp targets. The question of other record kinds is unchanged.
Filed 2026-10-25 by session f4 from the v3-validation lane (design section
3.4). N1 must stay limited to temp targets until NightscoutKit accepts both
spellings, or Loop would drop BG Check and Meal Bolus records it reads today.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MOD-UNITS-CANONICAL` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
