# Release readiness — cgm-remote-monitor 15.0.9, and the road after it

*Contributor-facing; written for the maintainer deciding the release and for
reviewers of PR #8598. Measured 2026-09-22 against `origin/dev` `74fc6619`,
`origin/master` `92d08342` (tag `15.0.8`), nightscout-connect `official/dev`
`8e26786`. Meets [DEFINITION-OF-DONE](../../00-overview/DEFINITION-OF-DONE.md).
Supersedes [the 2026-09-14 readiness snapshot](cgm-remote-monitor-release-readiness-2026-09-14.md)
for 15.0.9 and [the 2026-09-15 roadmap](../post-phase0-roadmap-2026-09-15.md)
for ordering.*

> **Connector status, later on 2026-09-22:** connector PR #64 merged into connector `dev` as
> `d208c7d`, carrying #61, #66 and #67 (steps 1 and 2 of §5.2, and #66). PR #68 is under review.
> Current state: queue items `P0-TAG`, `P0-F` and `P0-PIN` in
> [`queue/work-queue.yaml`](../../../queue/work-queue.yaml).

## 1. Verdict

**15.0.9 is ready to release from an engineering standpoint. What it's waiting
on is three decisions and one review, not more code.** A release today fixes
the credential-logging leak and two security issues. Those fixes are already
public on `dev`, but every operator running 15.0.8 still has the old behaviour.
Each day without a release extends that exposure without adding safety. That is
the strongest argument for timing.

| | state | reproduce |
|---|---|---|
| Content | 48 first-parent merges; 200 files, +14 381 / −1 262 | `git log --first-parent --merges official/master..official/dev` |
| Topology | `master` is an ancestor of `dev`; 308 behind, 0 ahead. The merge is a fast-forward in content | `git rev-list --left-right --count official/master...official/dev` |
| CI at the exact tip | 27 success, 3 skipped (matrix placeholders), 0 failed, on `74fc6619`: Node 20/22/24 × MongoDB 4.4/5/6, CodeQL, Docker build amd64+arm64 | `gh api repos/nightscout/cgm-remote-monitor/commits/74fc6619…/check-runs` |
| Mergeable | `MERGEABLE` | `gh pr view 8598 --json mergeable` |
| Human review | **`REVIEW_REQUIRED`, zero reviews** | `gh pr view 8598 --json reviews` |

## 2. What 15.0.9 contains

The authoritative, grouped list is
[`releases/cgm-remote-monitor-15.0.9/contents.md`](../../../releases/cgm-remote-monitor-15.0.9/contents.md);
defect detail is in the [backfix register](../remedial/nightscout-backfix-register.md).
In summary:

- **Thirteen backfix PRs** (twelve from this programme, one external): #8733, #8734, #8735, #8736,
  #8737, #8738, #8739, #8740, #8743, #8744, #8745, #8746, plus #8741 from an
  external contributor. Between them they close 27 register defects for operators
  once released. These cover query correctness (`$exists`, typed filters,
  `count=0` returning a whole collection), the v1 operator allowlist (BF-04,
  BF-70), alarm delivery (the insulin-age urgent alarm that could never fire),
  the bolus-calculator quick pick loading the wrong food (BF-35), the page
  failing to load on a bare URL flag, a read of ten entries copying 48 hours of
  data, credential settings silently converted to numbers, and three socket
  authorization defects (GHSA-gjhc / BF-79, GHSA-8849 / BF-75, BF-76, and the
  world-readable warning BF-77).
- **The credential-logging fix (BF-42, BF-43), carried in by the connector pin.**
  15.0.8 pins nightscout-connect v0.0.13, which writes CGM-service credentials,
  session tokens and readings to the server log on every start. `dev` pins
  `234d47c`, which deletes those call sites. The queue's `BFQ-CONNECTOR` gate
  fails on `master` and passes on `dev` (the control).
- Other contributors' fixes (profiles, clock low-trend, treatments query errors,
  report and cache races, COB, A1c units, mobile UI), 16 dependency bumps,
  translations, and dropping MongoDB 4.4 from the README.

## 3. What has to happen before release

### 3.1 Decisions (the maintainer's)

| id | decision | recommendation |
|---|---|---|
| `RT-VERSION` | **The version number.** Under the [versioning policy](semver-and-release-versioning-policy-2026-09-15.md) this can't be a patch. `env.js` gains `DEBUG_LOGGING` and `CONNECT_DEBUG`, debug logging becomes off by default, and a new API file appears, which makes it at least minor. #8738 also makes API v1 reject any `count` that isn't a whole number ≥ 1 with HTTP 400 (`lib/api/index.js`); on 15.0.8, `count=0` returned the whole collection. The policy treats rejecting previously accepted input as major (§8.1). Separately, all five cut branches also say `15.0.9` in `package.json`, and they require a different Node floor. | **15.1.0**, with the `count` rejection listed as a deliberate breaking correction in the release notes (they already describe it). None of the rejected inputs had a correct meaning, and the one that mattered returned whole collections. Apply the policy strictly and it's 16.0.0. Either way, record the choice, and move the cut branches off `15.0.9` so two different builds don't share one version string. |
| `RT-D3` | **D3 5.16 → 7.9 ships under this release.** The D3 test suite drives the real renderer (24 passing), but deleting both treatment-drag clamps (`renderer.js:764`, `:770-771`) leaves it green. That boundary is never tested. Dragging a treatment changes its recorded time, and IOB/COB are computed from that time. | Don't block on a new test. Do a **manual browser check** before tagging: drag a treatment past each chart edge and confirm it clamps. Record the result in the release PR. |
| — | **MongoDB 4.4.** After #8516, the README says 4.4 is unsupported and that 15.0.7 was the last version to work with it. CI still tests 4.4 and passes. | Pick one before the release notes go out: drop 4.4 from the CI matrix, or soften the README to "untested". |

### 3.2 Review

PR #8598 has no reviews. The programme's own PRs merged without human review
too, so **#8598 is the first place a second person can look at the whole
set**. A reviewer who isn't the author should approve it. The reviewer packets
under `reports/reviewer-packets/` are scoped for that.

### 3.3 Checks (cheap; a person with a browser)

1. **Alarm delivery on a login-required instance** (from #8745). Start an
   instance with `AUTH_DEFAULT_ROLES=denied`, log in at the prompt, trigger an
   alarm, and confirm it arrives. No automated test covers this client path.
2. **The D3 drag check** above.
3. **The connector pin stays installable.** `234d47c` is in connector `dev`
   since `d208c7d` (#67 merged with a merge commit, 2026-09-22), so it stays
   reachable; it is in no connector tag. The connector repository allows squash merges and has
   used them (#72). If #67 is squash-merged and the branch deleted, the commit
   15.0.9 pins could become unreachable, and installs from its archive URL could
   start failing. Before tagging, either merge #67 with a merge commit or put a
   tag on `234d47c`, or repin to an upstream `v0.0.14` that includes #64 and #67
   (§5.2).

### 3.4 Housekeeping that can go either way

- Crowdin PR #8730 (translations, 32 files) is open against `dev` and mergeable.
- `dev`'s `CHANGELOG.md` has a hand-written `[Unreleased]` section. That
  conflicts with the stated rule that the changelog is generated at release
  time. Either reconcile it at tag time (`releases/README.md` describes how) or
  retire the rule.
- Dependabot #8747 targets `master` with an axios bump that `dev` already
  contains (#8565). It becomes moot once #8598 merges.

## 4. What stays broken after 15.0.9

These should be stated plainly in the release notes. The generated
operator-exposure table in
[PROGRAMME-STATUS](../../00-overview/PROGRAMME-STATUS.md) is the live list. The
ones a reader should know by name:

- **BF-72.** A class of expensive search request can tie up the database for
  minutes. It needs no credentials on a default install, and no fix exists.
  Whether to invoke the security-contact process is an open decision (`BFQ-72`).
  Described by mechanism only; see the register.
- **BF-47.** An ordinary subject edit destroys stored fields. Whether that
  behaviour was intended has to be settled before code changes.
- **BF-86.** A low threshold entered in mmol/L on a mg/dL site (`BG_LOW=3.9`) is
  stored as 3.9 mg/dL with no warning, so the low alarm can never fire.
  Reproduced against the shipping `lib/settings.js`. BF-67 is the high-side
  version, where a threshold is silently rewritten; the two should be fixed
  together.
- **BF-85.** For CareLink via nightscout-connect, a "no reading" marker is stored
  as glucose 0. While it is the newest value, the high/low alarms aren't
  evaluated. Read-derived, not run. The connector fix (`8406edf`) is in upstream
  PR #64, not in upstream `dev` or in the pin 15.0.9 ships (§5.2).
- **BF-41.** A reading dated in the future silences the stale-data alarm.
- **BF-44, BF-45** (now low). MiniMed ingestion divergences that assumed a working
  mmconnect. The maintainer confirms it does not work, so neither causes a data
  problem in practice; cut 4 removes the dead path.

Nightscout isn't a medical device. An operator who relies on alarms should
always have a second way to see readings.

## 5. The road after 15.0.9

### 5.1 Release sequence

| order | release | content | state today |
|---|---|---|---|
| 1 | **15.0.9 / 15.1.0** | §2 | ready pending §3 |
| 2 | **Backfix 2** (patch on top) | `bf/auth` (P0-C, BF-17 plaintext token), `bf/throttle` (P0-J, BF-30 failed-auth throttling), connector pin to the upstream `v0.0.14` tag (§5.2) if 15.0.9 did not take it, BF-72's fix once chosen, BF-41/46/67/ENV as gates go green | `bf/auth` and `bf/throttle` are 9 behind `dev` and merge with **0 conflicts**; `bf/auth` needs a security reviewer, and none is assigned |
| 3 | **Cut 1** `chore/retire-jsdom` alone | test-infrastructure removal | 133 behind, 7 conflicting paths |
| 4 | **Cut 2** `chore/build-runtime-separation` | build/runtime split | 133 behind, 14 |
| 5 | **Cuts 3+5** `chore/compose-mongodb6` + `chore/nightscout-modernization` | dependencies, Node floor `^22.23.2 \|\| ^24.20.0` | 133 behind / 16; the integration branch is 9 behind / 1 (`lib/server/bootevent.js`) |
| 6 | **Cut 4** `chore/mime-exposure-review` | retires the legacy MiniMed and Dexcom bridges; nightscout-connect is the only ingestion path | 133 behind, 18. The separate deprecation release is no longer needed (§5.3) |

Conflict counts are `git merge-tree` of each tip against `dev` `74fc6619`. The
queue's `RT-REBASE` gate re-measures them.

**The rebase cost rises with every merge to `dev`, and it rises fastest right
after a release.** Every file that newly conflicts on cuts 2–4 was touched by the
backfix merges. The cheapest time to rebase cut 1 is immediately after 15.0.9
is tagged, while `dev` is quiet. Holding backfix 2 until cut 1 is rebased makes
that cost fall once instead of repeatedly.

### 5.2 nightscout-connect 0.0.14: land the fixes upstream, then pin a real tag

Upstream is releasing 0.0.14 from its `dev` through PR #70 (`dev` → `main`, head `8e26786`,
mergeable). Per the maintainer it brings substantial connectivity fixes, including confirmed
Dexcom access; the tree carries Glooko (#71), connector CI (#72) and LibreLinkUp v4 with
real-account validation (#73). **The programme's local `v0.0.14` tag should be retired, not
pushed.** Everything it carries already exists as an upstream PR:

| programme fix | upstream PR | state against `official/dev` `d208c7d`, 2026-09-22 |
|---|---|---|
| credential- and session-safe logging for Dexcom and MiniMed; internal payloads kept out of logs | **#64** | **merged** (`d208c7d`) |
| CareLink zero-reading filter (**BF-85**) and measurement-time status (`8406edf`, from #65) | carried in **#64** | merged |
| debug logging opt-in; the connector's own logger; reads `CONNECT_DEBUG` (`234d47c`) | **#67**, folded into #64 | merged |
| retry interval, delay cap and pool jitter (BF-08, BF-34) | **#68** | under review, head `635cc9f`, merges into `d208c7d` cleanly |
| release listeners and settle output waits on stop | **#66**, folded into #64 | merged |

*(Measured on `8e26786`, before #64 merged; `d208c7d` has `lib/logging.js`.)* **Upstream `dev` at
`8e26786` would have regressed 15.0.9.** It has no `lib/logging.js`, and it logs
CareLink login responses (headers and bodies) and Dexcom Share error bodies unconditionally.
That is the BF-42/BF-43 behaviour that 15.0.9's pin `234d47c` removes. It also does not read
`CONNECT_DEBUG`, which 15.0.9 adds and documents. Measured: 135 unguarded `console.*` sites in
`lib/` on `8e26786`, 57 plus a fixed-message logger on `234d47c`, 144 on `v0.0.13`.

**Sequence:**

1. Merge **#64** into connector `dev`. It is mergeable now and closes the credential logging and
   BF-85.
2. Rebase and merge **#67**, so `CONNECT_DEBUG` works and debug output stays opt-in. Without it,
   repinning makes a documented 15.0.9 switch do nothing.
3. Merge #70, and tag and publish 0.0.14 from `main`.
4. Repin cgm-remote-monitor to the `v0.0.14` tag tarball. Gates: `BFQ-CONNECTOR` (credential
   logging) must pass on the new pin, and CI must be re-run. A tag also removes the
   reachability risk in §3.3.
5. #68 and #66 follow in 0.0.15.

**For 15.0.9 the choice is timing.** If steps 1–3 can happen promptly, repin 15.0.9 to the tag,
so users get the connectivity fixes and BF-85 in the same release. Otherwise ship 15.0.9 on
`234d47c` (tag that commit first) and repin in backfix 2. Either way, **do not repin to an
upstream 0.0.14 that lacks #64 and #67.**

### 5.3 Cut 4: mmconnect is dead, and Dexcom already moved in 15.0.8

The maintainer confirms that legacy mmconnect (`minimed-connect-to-nightscout`) does not work.
That is operational knowledge; the vendor API is not reachable from a local test. Dexcom was
already moved: since 15.0.8 (`a91e8ee4`, 2026-07-07), `BRIDGE_*` Dexcom settings are served by
nightscout-connect by default, with a deprecation warning, and `DEXCOM_BRIDGE_USE_LEGACY=true`
is the escape hatch. So:

- **Cut 4 deletes nothing a user has working.** The legacy MiniMed path does not work, and the
  legacy Dexcom path is already off by default.
- **The separate deprecation release (RT-4) is no longer needed.** 15.0.8 already shipped the
  Dexcom switch and its warning. The 15.0.9 release notes can announce the retirement of both
  legacy paths, and cut 4 can join the train after cuts 3+5.
- **What still gates cut 4:**
  - `MMCONNECT_*` settings must map to nightscout-connect's CareLink source (cut 4 implements
    `applyMmconnectToConnectCompatibility`);
  - BF-61, the whole-site boot error for leftover `MMCONNECT_*` settings, must be resolved;
  - BF-85 must be fixed in the connector, since CareLink through the connector becomes the only
    MiniMed path;
  - the `DEXCOM_BRIDGE_USE_LEGACY` users need a notice before the escape hatch disappears.
- **BF-44 and BF-45 are re-graded to low** in the register. Both assumed two working ingestion
  paths at once.

### 5.4 Multitenancy

Decisions D1–D17 are recorded in the
[execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).
D17 row 2 (Ory Kratos as a shared human-identity pool) is held pending
`T30-ORY-PROOF`. Tenancy work is based on `chore/nightscout-modernization` (D9),
so **no tenancy code reaches a release before step 5 above**. That bounds the
schedule more than anything in the tenancy plan does.

- **Now unblocked.** The seam rebase (roadmap R5) was waiting for Phase 0 to be
  on `dev`, and it is. `seam/t1-2-storage-interface` is 68 behind its base
  (`chore/nightscout-modernization`) with 19 conflicting paths (`SEAM-REFRESH`,
  red). This drift gets worse on its own, so it should be scheduled.
- **Claimable now.** `T30-SCHEMA-CRED` (per-tenant root credential, D14 signing
  key, device tables) has no blockers.
- **Waiting on proof.** `T30-ORY-PROOF`. Stand up Kratos + Hydra with two
  tenants against one pool, and confirm with a control that tenant A's session
  can't be exchanged for a token on tenant B. No human-identity DDL until that
  is done.
- **Off by design.** Alarms are off under `TENANCY_MODE=multi` until plan §7a's
  list is done.

### 5.5 The binding constraint

In the queue, 69% of items route to the maintainer, and the SECURITY and SAFETY
rows name a kind of reviewer with no one assigned. The modernization branches
and the release PR have no human reviews. More engineering won't move the
release train. Recruiting two reviewers will: one security, one clinical-safety.
Onboarding for them is in
[REVIEWER-ONBOARDING](../../00-overview/REVIEWER-ONBOARDING.md).

## 6. Draft status

This is a draft for maintainer review. Before relying on any count here, re-run
the command next to it. The facts most likely to have changed are the CI state
(if `dev` moves), the connector trees, and the conflict counts.
