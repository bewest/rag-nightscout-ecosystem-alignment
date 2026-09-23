# 15.0.9 close-out and backfix 2: branch and PR plan

*Contributor-facing. Living document: it is updated as each unit lands and the
queue (`queue/work-queue.yaml`) is authoritative for item state. Measured
2026-09-22 against cgm-remote-monitor `origin/dev` `74fc6619`, `origin/master`
`92d08342` (tag 15.0.8), `origin/chore/nightscout-modernization` `b1bdaca0`, and
nightscout-connect `official/dev` `1946beb`. Re-run the command beside any count
before relying on it.*

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

| branch | content | reviewer | waits on |
|---|---|---|---|
| `bf/connect-pin-0.1.0` (`338deb7f`, pinned to `0.1.0-dev.1`) | exact `nightscout-connect` `0.1.0` pin + regenerated lockfile (P0-PIN, P0-LOCK) | maintainer | connector tag `v0.1.0` (P0-TAG) |
| `docs/mongodb-floor` (`aabce4b1`, prepared) | `dev`'s README (from #8516, merged 2026-09-04) says MongoDB 4.4 is *not supported*, but CI tests 4.4, 5.0 and 6.0, and the full suite passes on 4.4.24 exactly as on 7.0.43 (2386/0/3). 15.0.8's README says "4.4 or later". The branch marks 4.4 as deprecated and still tested, which is the wording a reviewer asked for on #8516. Follow-up, not prepared: add 7.0 to the CI matrix | maintainer | nothing |
| `bf2/backports` (`b5038500`; moved here 2026-09-23) | the two modernization-only security fixes that reproduce on `dev` and 15.0.8 (alarm-socket credential logging; per-collection read grant on two shared routes), content-identical cherry-picks | security reviewer | nothing |
| `bf/count-zero-empty` (`ce9503ac`; `7b32d9ab` pushed) | `?count=0` answers `[]` on v1 reads; saves and updates ignore `count`; deletes keep dev's refusal (RT-COUNT0) | maintainer | nothing |
| `bf/qs-6.16` (`46b20b38`) | both `qs` overrides to 6.16.0 (BF-87) | maintainer | nothing |

Evidence prepared for human sign-off, not code:

- **RT-D3**: an automated browser drag of a treatment on 15.0.8 and on `dev`. It
  records the treatment's stored time before and after. The drag check stays a
  human decision; the automation gives it evidence.
- **`/alarm` client path under `AUTH_DEFAULT_ROLES=denied`**: authenticate at the
  prompt, fire an alarm, confirm it arrives. No test covers this.
- **15.0.9 release notes**: the connector 0.1.0 changes, #8738 and #8743 as
  declared corrections, and the retirement notice for the legacy MiniMed and
  Dexcom bridges (RT-4 folded in).

### Backfix 2 (into 15.0.9, decided 2026-09-23; see §1a)

| branch | content | reviewer |
|---|---|---|
| `bf2/auth-hardening` | `bf/auth` + `bf/throttle` refreshed onto `dev`, plus the `client-ip.js` backport behind `TRUST_PROXY` with today's behaviour as the default; flag registry entries; P0-C-REMEDIATE's operator text | security reviewer (none assigned) |
| `bf2/ops` | BF-10 compose `ulimits`, FU-RESIDUALS follow-ups 3 and 7, BF-63 error-renderer fix | maintainer |
| BF-72 | no branch in any public repository; a private recommendation first | security reviewer; disclosure route is the maintainer's |

BF-47 (the subject-field allow-list on `bf/auth`) was decided on 2026-09-23 (§1a): the
allow-list is intended and stays, with no compatibility flag. The remaining defect is the
admin page, which clears `notes` and `created_at` on every edit (BFQ-47).

**Integrated 2026-09-23** on scratch `rc/backfix-2` `e9a4ef62`, pinned to `dev` `74fc6619`: `bf2/ops`, then
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
path. Which normalisation the cuts keep is an open decision, recorded on RT-3.

**Decided 2026-09-23: no flag for BF-47.** The maintainer ruled that the allow-list is the declared schema for subjects and roles, so fields outside it are not part of the contract. The paragraph below is kept as the option that was considered.

**Considered, not adopted: BF-47.** A compat flag for the subject-field allow-list would look like
`AUTH_SUBJECT_FIELDS=passthrough|owned` (the name is illustrative). Under `passthrough` (the
default), `save()` strips only the token fields, which is enough for BF-17. Under `owned`, it writes
only today's allow-list. Adopting it would make `bf2/auth-hardening` a minor change instead of a
major one. It is the maintainer's decision.

## 5. Human steps, in order

Re-ordered 2026-09-23. State is in the queue; this is only the order.

1. **Connector:** open the PR for `fix/nightscout-reader-roles` (BF-89, P0-CONNECT-ROLE) into
   connector `dev`, and merge it.
2. **Connector:** fix BF-91 (BFQ-91). No branch exists yet.
3. **Connector:** tag a new prerelease from `dev` with both fixes, and test it for as long as
   the maintainer judges enough (P0-TAG). Then tag `v0.1.0` and approve the `npm-publish`
   environment.
4. **Nightscout:** push `bf/count-zero-empty`, `bf/qs-6.16`, `docs/mongodb-floor` and
   `bf2/backports`, and open a PR for each into `dev`. Merge them one at a time, evaluating
   between merges.
5. **Nightscout:** move `bf/connect-pin-0.1.0` from `0.1.0-dev.1` to `0.1.0` and regenerate the
   lockfile (P0-PIN, P0-LOCK). Push it, open its PR, and merge.
6. **Nightscout:** finish the 15.0.9 release notes. Get #8598 approved by at least one reviewer
   who is not the author, merge it, and tag 15.0.9.
7. **Advisories:** apply the metadata corrections (`advisories/apply-metadata.sh --apply`) at any
   time; they stay drafts. After 15.0.9 ships, restore the withheld write-ups from `ef376ecb`,
   send the replies, and publish.
8. **Backfix 2 (moved into 15.0.9, §1a):** once `rc/15.0.9-additions-c` is green, push `bf2/ops`,
   `bf2/auth-hardening` and `bf2/subject-edit-keeps-fields` and open their PRs before step 6, merging
   them one at a time like step 4.
