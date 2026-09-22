# Sequencing the five advisories and the two fixes — what can ship, in what order, through which channel

*Contributor-facing.*

> **Snapshot — describes 2026-09-21 (before the fixes merged), measured against cgm-remote-monitor
> `origin/dev` `59430336` and `v15.0.8` = `origin/master` `92d08342`.** Status: **superseded.** The
> vehicle was decided (§0) and all three fixes merged into `dev` on 2026-09-21 as public PRs —
> #8744 (`loadRetro`, BF-79), #8745 (`/alarm`, BF-75/BF-76), #8746 (readable-world warning, BF-77) —
> taking `origin/dev` to `74fc6619`. **None is released; 15.0.8 is still affected by GHSA-gjhc and
> GHSA-8849.** No security release was cut and no advisory has been published. Current state and
> what is still owed: [the disposition](./security-advisory-disposition-2026-09-21.md) §4;
> [`queue/work-queue.yaml`](../../../queue/work-queue.yaml) items `ADV-*` and `RT-0`.

Companion to [the disposition](./security-advisory-disposition-2026-09-21.md), which says *what
each advisory is*. This one says *how it ships*. Every constraint below was measured on
2026-09-21.

---

## 0. DECIDED 2026-09-21 — the vehicle is `dev`, and the PRs are public

Ben West: *"we're actively working on patches and PRs that will ship against dev imminently."*

That settles §3 and §5 below, which were written while the vehicle was open. They are kept
because the measurements in them stand and one of them is now a **backport option** rather than
a plan: all three fix commits cherry-pick cleanly onto `v15.0.8` and the suite there goes
**1533 → 1588, 0 failing**, so a 15.0.8 security patch remains available if the `dev` release
slips.

**One consequence to sequence deliberately.** A public PR against `dev` that says *"alarm
delivery went to the whole namespace"* **is** the disclosure. So:

- the advisories should be **published at or close to the moment the PRs go up**, not later.
  Publishing late is the worst case: the defect is legible in a public diff while the advisory
  that tells operators whether they are affected is still hidden;
- both PR bodies are written to carry that information themselves — in particular that a default
  `AUTH_DEFAULT_ROLES=readable` install has **zero** marginal exposure from either defect — so a
  reader who finds the PR before the advisory is neither alarmed nor falsely reassured;
- **this repository should be pushed after the PRs are opened, not before.** It is public, and
  it currently holds the fullest description of both defects anywhere.

## 1. The constraint that shapes everything

Two defects are **live on the shipping release with no patched version anywhere**:
`loadRetro` (BF-79 / GHSA-gjhc) and the `/alarm` broadcast (BF-75 / GHSA-8849). Both bypass
`AUTH_DEFAULT_ROLES=denied`. Neither advisory is published.

So the ordinary path for this project — open a PR on `nightscout/cgm-remote-monitor`, paste a
full explanatory body — **publishes a working attack before any release carries the fix**. That
is the BF-70 problem again, and worse: BF-70 was found and merged inside one day, whereas these
have no release vehicle yet.

There is a second constraint. **`github.com/bewest/rag-nightscout-ecosystem-alignment` is
PUBLIC**, so everything this programme commits about these two defects is published. See §5.

## 2. What exists right now

| artefact | where | state |
|---|---|---|
| `loadRetro` fix | `crm-adv-retro` `bf/ws-loadretro-auth` `9765e8cd` | 1 commit, tested, ablated, **unpushed, no upstream** |
| `/alarm` fix (shape B) | `crm-adv-alarm` `bf/alarm-socket-scope` `012f1623` | 2 commits, 51 tests, 5 ablations, **unpushed, no upstream** |
| superseded shape A | same worktree, `refs/backup/alarm-shapeA` `842d81fb` | keep until the rebuild is accepted, then delete |
| **the same fixes on `v15.0.8`** | `crm-adv-secrel`: `sec/loadretro-15.0.8` `e34642bd`, `sec/alarm-15.0.8` `bc8ec7b2`, and all three on `wip/security-release-15.0.8` `b02f2c85` | cherry-picked with `-x`, **suite green**, unpushed — these are the PR heads |
| reporter's `/alarm` fix | `nightscout/cgm-remote-monitor-ghsa-8849-qjp5-vrrj` **PR #1** | open since 2026-09-18, targets `master`, **does not close the bypass** — see §4 |
| `$where` fix (GHSA-r3gv) | `origin/dev`, merged as PR #8743 | **merged, unreleased** |
| XSS fixes | `v15.0.8` | **shipped** |
| BF-73, BF-74, BF-77, BF-78 | nothing | decisions, no branches |

## 3. The measurement that decouples the security response from the release train

The release train is stuck: `RT-0` (release 15.0.9) is `needs-decision` behind `RT-D3`, and
`dev` is **299 commits** ahead of `master`. If the only vehicle for a security fix were 15.0.9,
the fix would be hostage to a two-major charting upgrade and four release cuts.

It is not. Measured today:

- **`master` is a strict ancestor of `dev`** — 299 commits behind, **zero** ahead. A release from
  either is a fast-forward question, not a merge question.
- **The four files the fixes touch are byte-identical between `v15.0.8` and `dev`**:
  `lib/api3/alarmSocket.js`, `lib/server/websocket.js`, `lib/client/hashauth.js`,
  `lib/authorization/index.js`.
- **All three fix commits cherry-pick cleanly onto `v15.0.8`**, verified in a throwaway worktree.

**So a minimal security release carrying only these fixes is available**, without shipping the
299-commit backlog and without waiting on RT-D3. The reporter reached the same conclusion
independently — their PR targets `master`.

**And the gate is now met.** Measured on `v15.0.8` with its own `npm ci` install and a
dedicated mongod 7.0: **1533 passing / 0 failing** at the tag, **1588 passing / 3 pending / 0
failing** with the three fixes cherry-picked. The delta is **55**, exactly the new cases — 4 for
`loadRetro` and 51 for `/alarm` — and **no existing test broke**. For comparison the same fixes
on `dev` go 2311 → 2315 and 2311 → 2362, also 0 failing; the two trees differ in total because
`dev` carries 299 commits of additional tests.

So the minimal security release is an option, not a plan.

### 3.1 The version number is already contested and this makes it worse

`dev`'s `package.json` already says **15.0.9**, and `RT-VERSION` is an open queue item recording
that two artefacts claim that number with different Node floors. A security release from
`master` needs a number, and taking 15.0.9 collides with `dev`'s claim. Two coherent answers,
both of which someone has to choose:

- **Security release is 15.0.9 from `master`**; `dev` bumps to 15.0.10 and the tag merges back.
- **Security release is 15.0.8.1 / 15.0.9-security from `master`**; `dev` keeps 15.0.9.

A third answer — release `dev` as 15.0.9 with everything — is the train's plan and is blocked.

Note also that `master` carries **two tags for the same commit**, `15.0.8` *and* `v15.0.8`.
Whatever is cut should pick one spelling deliberately.

## 4. The reporter's PR has to be reconciled, not ignored

`advisory-fix-1` is a good-faith fix from the person who reported the defect, and it is the
first thing a reviewer will find. Measured, it does not close the bypass: it gates on
`AUTHENTICATION_PROMPT_ON_LOAD` rather than `AUTH_DEFAULT_ROLES`, so on a hardened instance with
the prompt flag at its default a never-subscribing socket still receives everything; and where
it does engage it never consults `api:*:read`, so a write-only token hears every alarm while
being refused every REST read in the same run. Detail and controls in
[the evaluation](../../60-research/remedial/ghsa-8849-reporter-pr-evaluation-2026-09-21.md).

**The recommendation is to reply, not to close.** The finding is entirely theirs, nobody inside
the project had it, and the mistake they made is the one this whole week has been about: the
product has two authorization-shaped settings and the intuitive one is not the boundary. Credit
them on the published advisory. Offer the Foundation's branch as the merge candidate with the
two measurements as the reason.

## 5. Channel, per artefact

GitHub has already created **private temporary forks** for three advisories —
`…-ghsa-gjhc-pc29-r3m6`, `…-ghsa-8849-qjp5-vrrj`, `…-ghsa-5mrq-gpqw-q5v5`. There is **none** for
GHSA-r3gv or GHSA-mjp4. A PR into a private fork is invisible to the public and GitHub can merge
it and publish the advisory as one action.

**SUPERSEDED for the two fixes by §0** — they go as ordinary public PRs against `dev`. The
private forks remain the right place to *reply to the reporter*, and the table is kept because
the reasoning still applies to anything found later.

| what | channel | why |
|---|---|---|
| `loadRetro` fix | ~~private fork~~ → **public PR against `dev`** | decided §0 |
| `/alarm` fix | ~~private fork~~ → **public PR against `dev`**; reply to the reporter in `…-ghsa-8849-qjp5-vrrj` | decided §0 |
| BF-77 (warning), BF-78 (careportal) | **ordinary public PR** | neither is exploitable; BF-78 fails closed |
| BF-73 (error page), BF-74 (v3 settings) | **ordinary public PR**, after the decisions | the code is already public and neither adds reachability |
| advisory metadata corrections | GitHub advisory UI/API | not code |
| this programme's documents | **held** — see below | they describe two live unpatched bypasses |

### 5.1 The alignment repo's own documents need a holding decision

Seven register entries (**BF-73 … BF-79**) and six research documents are in the working tree
and **none is public yet** — verified against `origin/main`. Of those, the ones describing
BF-75, BF-76 and BF-79 state, in plain language, that a live shipping release leaks medical data
to an unauthenticated socket and that the documented hardening does not stop it. Committing them
publishes that before any fix exists.

**Recommended split:**

- **Hold until the advisories publish**: the BF-75 / BF-76 / BF-79 register rows and detail
  sections; `ghsa-gjhc-loadretro-*`; `ghsa-8849-alarm-socket-*`;
  `ghsa-8849-reporter-pr-evaluation-*`; §2.1, §2.2 and §5 of the disposition; §2 of the
  configuration matrix.
- **Safe to commit now**: `ghsa-xss-pair-verification-*` (both defects shipped fixed in 15.0.8);
  BF-77 and BF-78 (a suppressed warning and an inert role, neither exploitable); BF-73 and BF-74
  (both visible in public source and neither newly reachable); the ADV-* queue items **minus**
  the fields that quote the socket behaviour.
- **Mechanically**: the safest holding place is where the probes already live — outside version
  control, in the session scratchpad — with a single tracked placeholder naming what is withheld
  and why, so the register does not silently appear to have a gap.

**This is a human decision**, because it trades the programme's own convention — that
everything is written down publicly and promptly — against a disclosure window. It is the same
trade BF-70 recorded, at larger scale.

*[Outcome: overtaken. The fixes merged publicly into `dev` on 2026-09-21, so the defects are
legible in public diffs; the question that remains is advisory publication, not holding these
documents.]*

## 6. The order

Numbered because each step's output is the next step's input.

1. ~~**Run the suite on `v15.0.8` + the three fix commits.**~~ **DONE 2026-09-21: 1533 → 1588
   passing, 0 failing, delta exactly the 55 new cases.** The minimal security release is
   available. Branches are cut and named in §2.
2. **Do the manual browser check** on a shape-B `denied` build: load, authenticate at the prompt,
   fire an alarm, confirm it arrives. No test covers it and it is the path that could silently
   drop a real hypo alarm.
3. **Decide the holding question** in §5.1, so the programme can keep recording without
   publishing.
4. **Decide the version number** in §3.1.
5. **Open the two fix PRs in the private forks**, and reply to the reporter's PR with the
   measurements.
6. **Cut and tag the security release**; publish the two advisories at the same moment, with
   corrected metadata and the reporter credited.
7. **Then** the public PRs for BF-77 / BF-78, and the decisions on BF-73 / BF-74.
8. **Then** revisit GHSA-r3gv: its `$where` fix is merged to `dev` and unreleased, so the same
   release question applies to it, and its advisory metadata names a package that does not exist.

Steps 1 and 2 are measurements. Steps 3 and 4 are decisions. Nothing is engineering.

*[Outcome as of 2026-09-22: step 1 done. Step 5 was replaced by §0 — public PRs against `dev`,
merged 2026-09-21 as #8744/#8745/#8746. Steps 2, 4 and 6 are not done: the manual browser check
has not been performed, no version was chosen, no security release was cut, and no advisory is
published. The reporter reply (step 5) and the metadata corrections are drafted in
[`advisory-response-2026-09/`](./advisory-response-2026-09/README.md) and unsent. Step 7: BF-77
merged in #8746; BF-73/BF-74/BF-78 await decisions. Step 8: `$where` fix (#8743) merged, not
released.]*

*Evidence*: [disposition](./security-advisory-disposition-2026-09-21.md) ·
[configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md) ·
[loadRetro](../../60-research/remedial/ghsa-gjhc-loadretro-2026-09-21.md) ·
[alarm socket](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md) ·
[reporter PR evaluation](../../60-research/remedial/ghsa-8849-reporter-pr-evaluation-2026-09-21.md) ·
[XSS pair](../../60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md) ·
[register](./nightscout-backfix-register.md) · `queue/work-queue.yaml` items `ADV-*`
