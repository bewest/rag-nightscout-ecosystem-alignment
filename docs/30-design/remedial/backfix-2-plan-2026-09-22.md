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
| `bf/connect-pin` | exact `nightscout-connect` `0.1.0` pin + regenerated lockfile (P0-PIN, P0-LOCK) | maintainer | connector tag `v0.1.0` (P0-TAG) |
| `docs/mongodb-floor` (if the measurement says so) | README's MongoDB floor made to match what CI runs (#8516) | maintainer | measurement against a `mongo:4.4` container |

Evidence prepared for human sign-off, not code:

- **RT-D3**: an automated browser drag of a treatment on 15.0.8 and on `dev`. It
  records the treatment's stored time before and after. The drag check stays a
  human decision; the automation gives it evidence.
- **`/alarm` client path under `AUTH_DEFAULT_ROLES=denied`**: authenticate at the
  prompt, fire an alarm, confirm it arrives. No test covers this.
- **15.0.9 release notes**: the connector 0.1.0 changes, #8738 and #8743 as
  declared corrections, and the retirement notice for the legacy MiniMed and
  Dexcom bridges (RT-4 folded in).

### Backfix 2 (prepared now; PRs opened after 15.0.9 is tagged)

| branch | content | reviewer |
|---|---|---|
| `bf2/auth-hardening` | `bf/auth` + `bf/throttle` refreshed onto `dev`, plus the `client-ip.js` backport behind `TRUST_PROXY` with today's behaviour as the default; flag registry entries; P0-C-REMEDIATE's operator text | security reviewer (none assigned) |
| `bf2/backports` | whichever §2.1 commits reproduce as defects on `dev` | security reviewer |
| `bf2/ops` | BF-10 compose `ulimits`, FU-RESIDUALS follow-ups 3 and 7, BF-63 error-renderer fix | maintainer |
| BF-72 | no branch in any public repository; a private recommendation first | security reviewer; disclosure route is the maintainer's |

BF-47 (the subject-field allow-list on `bf/auth`) is still `needs-decision`. The
flag rule suggests a compatibility flag that preserves fields today's `save()`
keeps, because third-party tools may rely on that. The maintainer has not ruled
on it, and until they do the branch keeps the allow-list as written.

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
| `TRUST_PROXY` | today's proxy behaviour (trust forwarded headers) | explicit trusted-proxy list | not yet planned | `bf2/auth-hardening` |
| throttle keying (name to be taken from `bf/throttle`) | today's behaviour | keyed on the trusted client address | the same release as `TRUST_PROXY` | `bf2/auth-hardening` |

## 5. Human steps, in order

1. Tag connector `v0.1.0` on `dev` and approve the `npm-publish` environment.
2. Push `bf/connect-pin` and open its PR into `dev`; merge.
3. Review and approve #8598 (at least one reviewer who is not the author); merge;
   tag 15.0.9.
4. Send the drafted advisory replies and metadata corrections
   (`docs/30-design/remedial/advisory-response-2026-09/`).
5. Push the backfix-2 branches and open their PRs.
6. Decide BF-47 and BF-72's disclosure route.
