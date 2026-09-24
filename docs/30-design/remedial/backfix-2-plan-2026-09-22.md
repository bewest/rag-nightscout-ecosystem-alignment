# 15.0.9 close-out and backfix 2: branch and PR plan

*Contributor-facing. Living document: it is updated as each unit lands and the
queue (`queue/work-queue.yaml`) is authoritative for item state. Measured
2026-09-22 against cgm-remote-monitor `origin/dev` `74fc6619`, `origin/master`
`92d08342` (tag 15.0.8), `origin/chore/nightscout-modernization` `b1bdaca0`, and
nightscout-connect `official/dev` `1946beb`. Re-run the command beside any count
before relying on it. §3 and §5 were re-measured on 2026-09-23 against `origin/dev` `4011193e`.*

BF-72 appears here by mechanism only. It is live on the shipping release, has no
fix, and this repository is public; the reproducing material is kept outside
version control.

## 1. Decisions taken 2026-09-22

| id | decision | consequence |
|---|---|---|
| RT-VERSION | The dev → master release is **15.0.9**, the number `dev`'s `package.json` already carries. | #8738 (v1 `count` below 1 answers HTTP 400) and #8743 (v1 operator allowlist) ship as-is, declared as corrections in the release notes. No compatibility flag is retrofitted onto either. |
| P0-TAG / P0-PIN | nightscout-connect **0.1.0 is tagged and pinned inside 15.0.9**. | `bf/connect-pin` is prepared now against `0.1.0-dev.1` and becomes a one-line change to `0.1.0` when the tag is published. |
| BFQ-72 | Candidate remedies are **measured privately**. | Branches and benchmarks live in gitignored scratch space. Nothing about BF-72 goes into a PR, an issue or a tracked file beyond the mechanism already in the register. |
| flag rule | **Fixes where the old behaviour is itself the defect ship on by default. A compatibility flag, defaulting to today's behaviour, is used where a legitimate deployment may depend on the old behaviour**, and it has a planned release in which its default flips. | This rule applies first to client-address trust (`TRUST_PROXY`) and the failed-authentication delay (BF-30). Other areas are decided case by case, and each case is recorded in §4. |

## 1a. Decisions taken 2026-09-23

These amend §1 where they overlap. Item state stays in the queue.

| id | decision | consequence |
|---|---|---|
| RT-COUNT0 | **`?count=0` answers an empty list.** Malformed counts (`abc`, `-3`, `2.5`, `1e2`, `0x10`, values above `Number.MAX_SAFE_INTEGER`) still answer HTTP 400. Saves and updates ignore `count`. **Deletes keep dev's rule** (amended 2026-09-23, same day): a count that is not a whole number of 1 or more, `0` included, is refused and nothing is deleted, because `count` never limits a delete and "delete zero" must not become "delete everything". | Amends #8738 before 15.0.9 is tagged. §1's "#8738 ships as-is" no longer holds; #8743 still does. |
| P0-TAG / P0-PIN | **0.1.0 is pinned in 15.0.9, after the prerelease has been tested for longer.** BF-89 (the Nightscout source sends `role` for `roles`) is fixed in connector dev before the full release. | Tagging waits for the testing and for `P0-CONNECT-ROLE`. `bf/connect-pin-0.1.0` stays on `0.1.0-dev.1` until then. |
| RT-4 | **No separate deprecation release.** | The legacy-ingestion notice goes in 15.0.9's release notes. |
| MongoDB 4.4 | **Deprecated in 15.0.9, dropped later.** | The release notes say it is deprecated. |
| RT-D3 | **A manual check plus an automated browser test.** | First automated run: [browser evidence](../../60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md). The manual check is still owed. |
| cut numbering | **Each cut is renumbered when it is rebased.** | RT-VERSION's collision gate stays red until then. |
| BFQ-72 | Disposition decided. | Held outside version control, as in §1. |
| ADV-CONFIG | **BF-78 is documented and warned about at boot.** | No behaviour change. |
| ADV-XSS-META | **Apply all four metadata corrections to the draft advisories.** | A human runs `advisories/apply-metadata.sh --apply`; the advisories stay drafts. |
| advisory write-ups | **Trimmed to match the shortened PR descriptions** of #8743, #8744 and #8745 until a release with the fixes ships and the advisories are published. | Done in `dcb04102`; the full text is at `ef376ecb`. |
| FU-PRBODIES | **Fix only the dead links in #8734–#8737.** #8739's file follows its live body. | #8743–#8745 are not touched until release. |
| P0-C | **The security reviewers are the maintainer and Andy.** | |
| BFQ-09 | **Measure first, then decide.** The maintainer leans towards zero being a real value. | The measurement must check the AAPS rapid-zero-temp display problem (`bec641ca`) does not come back. |
| BFQ-41 | **The stale-data check ignores a future-dated reading**, keeping the reading as sent. The tolerance is configurable, default 5 minutes. Snoozes run on the wall clock. An evaluator may take an "as of" time, but never for live alarms. | A7A-7 is the maintainer's to write up. |
| BFQ-47 | **The subject allow-list is intended.** | The fix is the admin page, which clears `notes` and `created_at` on every edit. |
| BFQ-52 | **The age push is sent once, even if the exact check is missed.** | Today's exact-match check becomes a defect to fix. |
| tenancy | Taken up in a separate session later. | |
| backfix 2 scope | **Backfix 2 ships inside 15.0.9**: `bf2/ops`, `bf2/auth-hardening` and `bf2/subject-edit-keeps-fields`. Supersedes §3's "PRs opened after 15.0.9 is tagged". | Integrated with the other 15.0.9 additions on a scratch `rc/15.0.9-additions-c`, with the combined suite and break-its run there before any PR opens. The release notes declare BF-47's allow-list as a correction, name `TRUST_PROXY`, and carry P0-C-REMEDIATE's text. |
| P0-TAG exit | **Lab soak, then the maintainer's judgement.** The soak includes a seeded source Nightscout and a second lab Nightscout syncing from it through the connector's Nightscout source. | The soak is evidence for the tag; it does not replace the decision. |
| backfix 3 | **Build BFQ-41, BFQ-52, BFQ-90 and BFQ-69, and measure BFQ-09**, on local branches off `dev`. | Destination release not yet decided. |
| 15.0.9 ID consistency | **15.0.9 ships consistent, working create, read, update and delete by `_id` across the API, and connector Nightscout-to-Nightscout sync working well, if feasible.** `bf/object-id-consistency` (BF-99 to BF-102) goes in instead of the narrow `bf/profile-object-id`. | BFQ-102 is a 15.0.9 unit and BFQ-99 is superseded by it. Remaining CRUD gaps found beside it (entry re-POST 500, websocket `dbAdd`, route-level id patterns) are measured and fixed on top of it where feasible. The connector's bounded profile fetch and update-on-change are tested against a sink on that branch. The combined rc re-run includes it. |
| 15.0.9 CRUD decisions (BFQ-102) | **D1**: devicestatus create gets BF-99's check, so a re-send of a text-stored `_id` collides as on dev instead of adding a copy. **D2**: API v3 reaches v1 records with a non-hex `_id`, as `lib/api3/swagger.yaml` documents. **D3**: an entries POST that matches an existing reading answers with the stored `_id`. **D4**: an upper-case hex string stored on disk is found only when asked in upper case; this is documented, not changed. | Built on `bf/object-id-crud` after `c721e202`; the matrix expects all four. |
| connector profile sync (BFQ-97) | **The bound stays at the newest profile plus those saved since the last poll**, so an API edit that leaves `created_at` unchanged on an older profile is not copied. **No backfill**: a new receiving site starts from the 2-day window, as entries and treatments do. **The source wins**: a profile edited on the receiving site is overwritten when the source's copy changes. | `fix/profile-sync-bounded-update` needs no change for these; the PR body and 15.0.9 release notes say the third in plain words. |
| BF-103 (split drag) | **Goes into 15.0.9 if `bf/split-drag-time` comes back clean**: the fix is on the browser side (the split copy drops the page's `mills`, `date`, `mgdl` and `scaled`; a move clears a stored time that disagrees with the new one), plus a read-only query to find damaged records. The server-side options (a read-time rule in `ddata`, stripping on websocket writes) are measured, not built. | Clean means red on dev and green on the branch, a green full suite, every break-it red, and clean merges with the open 15.0.9 PRs. If any of these fails, BF-103 ships as a known issue whose advice is to avoid splitting by drag. Editing the time is not advised until it is measured to correct the stored time. |
| modernization | **Prepare the cuts now, against the 15.0.9 rc**; ship them after 15.0.9. Whether they ship as separate releases or as one combined major is still open. | The rehearsal reports per-cut conflicts, suites and the BF-58 image result, so that choice can be made on numbers. |

## 2. Where each piece of backfix 2 comes from

Most of backfix 2 was built on `dev` and needs only a refresh. One part lives only
on the modernization branch and has to be factored out.

| unit | source | against `dev` `74fc6619` |
|---|---|---|
| `bf/auth` (P0-C, BF-17, BF-47) | `dev` | 9 behind, 0 conflicting paths |
| `bf/throttle` (P0-J, BF-30) | `dev` | 9 behind, 0 conflicting paths |
| client-address trust (`lib/server/client-ip.js`, `TRUST_PROXY`) | modernization only: `06c83f2f`, then `395f3207` restores proxy compatibility by default | not on `dev`; must be extracted |
| BF-10 compose `ulimits`, FU-RESIDUALS, BF-63 (`dev` half) | new, on `dev` | not started |

Reproduce: `git rev-list --count bf/auth..origin/dev`;
`git merge-tree --write-tree --name-only origin/dev bf/auth`.

**BF-30 is not closed by `bf/throttle` alone.** Its address key is still one the
caller can choose. The key becomes trustworthy only when the client address comes
from a configured trust boundary, which is what `client-ip.js` provides. So the
auth-hardening unit is `bf/auth` + `bf/throttle` + a backport of `client-ip.js`.
Both the proxy trust and the throttle keying default to today's behaviour under
the flag rule.

### 2.1 Security-shaped commits that exist only on the modernization branch

The modernization branch is 498 commits ahead of `dev`
(`git rev-list --count origin/dev..origin/chore/nightscout-modernization`). Six
commits in that range change authorization, credential handling or header
policy. **None has yet been shown to fix a defect present on `dev`.** Each needs a
reproduction on `dev`, with a control, before it becomes a backport.

| commit | subject | cherry-picks onto `dev` |
|---|---|---|
| `31c354d8` | Stop logging alarm subscription credentials | clean |
| `d3ac8026` | enforce read permissions for selected count and slice storage | conflicts |
| `973a2849` | Keep status bootstrap credentials out of URLs and verify delete query guards | conflicts |
| `71c42c9a` | restrict authorization reloads to complete snapshots | conflicts |
| `d48be5e5` | preserve authorization editor drafts after failed saves | conflicts |
| `ad4a8cd5` | Compose explicit Helmet headers and centralize conditional CSP policies | conflicts; depends on the Helmet upgrade |

Measured with `git merge-tree --write-tree --merge-base=<c>^ origin/dev <c>`.

**Backports are made so that the modernization rebase stays trivial.** Where a
backport lands, it should carry the modernization commit's content unchanged
(`cherry-pick -x`) rather than a re-implementation. Then, when the cuts are
rebased, the two sides agree and only integration context conflicts.

## 3. Branches and PRs

A PR is grouped by the reviewer it needs. The failure policy is
`dev-cycle-review-decisions`: evaluate between each merge and skip-and-continue.
The units are integrated on a scratch `rc/backfix-2` branch pinned to `dev` by SHA.

### Into 15.0.9 (before the tag)

State on 2026-09-23 against `dev` `ddd9b600`. The queue holds the authoritative state; this is the list.

| PR | branch | content | state |
|---|---|---|---|
| #8750 | `docs/mongodb-floor` | README: MongoDB 4.4 deprecated, not unsupported (RT-MONGO-FLOOR) | merged |
| #8752 | `bf/connect-pin-0.1.0` | connector pin, exact `0.1.0-dev.2` (P0-PIN) | merged, superseded by #8759 |
| #8759 | `bf/connect-pin-0.1.0-dev.3` | connector pin, exact `0.1.0-dev.3` (P0-PIN; BF-97 and BF-98 fixed) | merged |
| #8757 | `bf3/mmconnect-deprecation-warning` | the MiniMed warning names its replacement settings (RT-4) | merged |
| #8749 | `bf/qs-6.16` | both `qs` overrides to 6.16.0 (BF-87) | merged |
| #8748 | `bf/count-zero-empty` | `?count=0` answers `[]`; saves and updates ignore `count`; deletes keep dev's refusal (RT-COUNT0) | merged |
| #8755 | `bf3/alarm-no-reading` | an alarm at a page with no reading no longer throws (BF-90) | merged |
| #8756 | `bf3/quickpick-rebuild` | the Bolus Wizard quick-pick list is rebuilt when the drawer opens (BF-69) | merged |
| #8753 | `bf2/ops` | compose `ulimits` (BF-10), the boot error page (BF-63 renderer half), Alexa default, `isPluginEnabled` | merged |
| #8751 | `bf2/backports` | the two modernization-only security fixes (BF-104, BF-105) | merged |
| #8760 | `bf/split-drag-time` | a treatment moved by drag, whole or split, keeps its new time for IOB and COB (BF-103) | merged |
| #8754 | `bf2/auth-hardening` | BF-17, BF-30, `TRUST_PROXY` (with hop counts and `true`), BF-47's admin-page fix; withheld-style body | **open**: security review, maintainer and Andy |
| #8758 | `bf/object-id-crud` | records keep their own `_id` across v1, v3 and the websocket (BF-99 to BF-102) | **open**: review |
| — | a pin to exact `0.1.0` | after connector `v0.1.0` is tagged (P0-TAG) | not started |

"merged" means merged into `dev`, not released.

**Tested together.** `rc/15.0.9-combined-36b` `d087588f` merged every PR above except #8760 and the final pin,
in PR order, each merge clean: 3015/0/3 on Node 20, 22 and 24 with MongoDB 4.4 and 7, the create/read/update/delete
matrix 336/336, and a Nightscout-to-Nightscout lab run on `0.1.0-dev.3` with no duplicates or gaps
([record](rc-15.0.9-combined-2026-09-23.md)). `dev` `ddd9b600` with #8754 (`ef3404fd`) and #8758 (`6d120fa2`)
merges clean and differs from that tree in exactly #8760's five files. Decided 2026-09-23 (maintainer): run
the combined suite on that set now, so #8754 and #8758 can merge on evidence, and once more after the pin to
exact `0.1.0`, before the tag. The first run is `rc/15.0.9-combined-59`.

**Checked by hand** on the combined rc `ec70aab0` (2026-09-23): the treatment drag (RT-D3) with mouse in mg/dL and
mmol/L and with touch, the same as 15.0.8; alarms under `AUTH_DEFAULT_ROLES=denied` and with
`AUTHENTICATION_PROMPT_ON_LOAD`; BF-90, BF-69, #8729, #8732 and the COB display. The drag check found BF-103
(a split drag keeps the old time), which is on 15.0.8 too. `ec70aab0` also carried #8754, which changes
`lib/api3/alarmSocket.js`; every other client file these checks use is identical on `dev` `4011193e`
([record](../../60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md)).

### Backfix 2 (into 15.0.9, decided 2026-09-23; see §1a)

| branch | content | reviewer |
|---|---|---|
| `bf2/auth-hardening` | `bf/auth` + `bf/throttle` refreshed onto `dev`, plus the `client-ip.js` backport behind `TRUST_PROXY` with today's behaviour as the default; flag registry entries; P0-C-REMEDIATE's operator text. Open as #8754 | the maintainer and Andy |
| `bf2/ops` | BF-10 compose `ulimits`, FU-RESIDUALS follow-ups 3 and 7, BF-63 error-renderer fix. Merged as #8753 | maintainer |
| BF-72 | no branch in any public repository; a private recommendation first | security reviewer; disclosure route is the maintainer's |

BF-47 (the subject-field allow-list on `bf/auth`) was decided on 2026-09-23 (§1a): the
allow-list is intended and stays, with no compatibility flag. The remaining defect is the
admin page, which clears `notes` and `created_at` on every edit (BFQ-47).

*Superseded by the combined rc above; kept as the record of the first integration.* **Integrated 2026-09-23** on scratch `rc/backfix-2` `e9a4ef62`, pinned to `dev` `74fc6619`: `bf2/ops`, then
`bf2/backports`, then `bf2/auth-hardening`, one `--no-ff` merge each, with no conflicts and nothing dropped. Suite
2386 → 2392 → 2404 → 2480 passing, 0 failing, on Node 20.20.0, and 2480/0/3 on 22.23.2, which is exactly the
additive total. Each unit's break-its still fail on the integrated tree. `rc/backfix-2` merges cleanly with
`bf/count-zero-empty` and `bf/connect-pin-0.1.0` (merge-tree only; the combined suite is owed on `rc/15.0.9-additions-c`,
because `bf/count-zero-empty` and `bf2/auth-hardening` both edit `lib/api/index.js`). Against the modernization branch it
conflicts in 12 paths. Record:
[backfix-2-integration-2026-09-23](backfix-2-integration-2026-09-23.md).

### After backfix 2: modernization

1. Rebase cut 1 (`chore/retire-jsdom`) immediately after 15.0.9 is tagged, while
   `dev` is quiet (readiness §5.1). Move its connector pin to `0.1.0` in the same
   pass (RT-CONNECT-PIN-CUTS, BF-65).
2. Cuts 2, then 3+5, then 4, each after the previous one lands. The backports in
   §2.1 make the cut-3+5 rebase cheaper, not dearer, provided they are
   content-identical.
3. `SEAM-REFRESH` after cuts 3+5, because tenancy is based on the modernization
   branch (D9).

## 4. Flag registry

Every compatibility flag is listed here with the release in which its default is
planned to flip. A flag without a planned flip is a permanent setting and has to
be documented as one.

| setting | default now | hardened value | planned flip | introduced by |
|---|---|---|---|---|
| `TRUST_PROXY` | unset: forwarded headers are believed from any peer. That is today's behaviour for client address, HTTPS detection and hostname, and the failed-authentication delay keys on the result | `false`, or an explicit list of proxy addresses/CIDRs | not yet planned | `bf2/auth-hardening` (`29e6430e`) |

**One flag, not two.** The throttle keys on `data.ip`, and `06c83f2f` already routes that through
`client-ip.js`, so the throttle's key follows `TRUST_PROXY` without a setting of its own. BF-30 is
closed only when `TRUST_PROXY` names a boundary. Under the default, the boot message says the delay
does not protect against guessing passwords or tokens.

**The unset default is dev's behaviour, not the modernization branch's.** `395f3207`'s unset
default differs from `dev` in four edge cases (BF-88), so `bf2/auth-hardening` keeps `dev`'s
resolution for the unset case (`8b975b41`) and uses `395f3207`'s code unchanged for the trusted
path. Decided 2026-09-23 (maintainer): the cuts keep this unset default too, not `395f3207`'s
normalisation; recorded on RT-3.

**Decided 2026-09-23: no flag for BF-47.** The maintainer ruled that the allow-list is the declared schema for subjects and roles, so fields outside it are not part of the contract. The paragraph below is kept as the option that was considered.

**Considered, not adopted: BF-47.** A compat flag for the subject-field allow-list would look like
`AUTH_SUBJECT_FIELDS=passthrough|owned` (the name is illustrative). Under `passthrough` (the
default), `save()` strips only the token fields, which is enough for BF-17. Under `owned`, it writes
only today's allow-list. Adopting it would make `bf2/auth-hardening` a minor change instead of a
major one. It is the maintainer's decision.

## 5. Human steps, in order

Re-ordered 2026-09-23, after ten of the twelve 15.0.9 PRs merged. State is in the queue; this is only the order.

1. **Review and merge #8754** (security review: the maintainer and Andy) and **#8758**. Neither conflicts with
   anything; merge #8758 last. Check `dev`'s CI after each.
2. **Connector 0.1.0:** when `0.1.0-dev.3` has had the testing the maintainer wants (P0-TAG), tag `v0.1.0` on
   connector `dev` and approve the `npm-publish` environment.
3. **Nightscout pin:** open the PR moving `dev` from `0.1.0-dev.3` to exact `0.1.0`, and re-run the combined rc
   with it (P0-PIN).
4. **Release:** finish the 15.0.9 release notes; get #8598 approved by at least one reviewer who is not the author;
   merge it; tag 15.0.9.
5. **Advisories:** the metadata corrections can be applied at any time (`advisories/apply-metadata.sh --apply`);
   they stay drafts. After 15.0.9 ships, restore the withheld write-ups and PR descriptions from `ef376ecb`,
   send the replies, and publish.
