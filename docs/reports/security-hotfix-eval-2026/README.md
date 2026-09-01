# cgm-remote-monitor Security Hotfix Evaluation (2026)

**Purpose:** Track methodical evaluation of externally-reported potential
security issues against `cgm-remote-monitor`'s `dev` branch, so a hotfix
release can be cut from existing `dev` work independently of any single
report's timeline. Each report gets its own findings/decision doc; this
README indexes them and tracks overall branch/worktree state.

**Working repo:** `nightscout/cgm-remote-monitor` (external, cloned under
`/home/bewest/src/worktrees/nightscout/`), not this repo. This repo
(`rag-nightscout-ecosystem-alignment`) hosts planning/decision records only —
code changes land as commits in the `cgm-remote-monitor` worktrees/branches
referenced below.

## Reports

| # | Title | Status | Branch/Worktree | Doc |
|---|-------|--------|------------------|-----|
| 1 | Stored XSS via WebSocket write purification bypass + unsafe `.html()` rendering | ✅ Fixed, tested, committed | `wip/bewest/security-hotfix-eval-stored-xss` (`cgm-dev-node22`) | [report-01-stored-xss.md](./report-01-stored-xss.md) |
| 2 | Auth-failure delay keyed on spoofable `X-Forwarded-For` (+ one-shot cleanup timer) | 🔎 Under evaluation, plan drafted | `wip/bewest/security-hotfix-eval-auth-delay` (`cgm-auth-delay-eval`) | [report-02-auth-delay-headers.md](./report-02-auth-delay-headers.md) |

## Conventions

- One branch per report, all forked from the same known-good `dev` tip
  (`4982e954`, PR #8558 merge) so each fix is independently reviewable,
  revertable, and mergeable without coupling unrelated CVEs together.
- Each report gets a dedicated worktree under
  `/home/bewest/src/worktrees/nightscout/` with `my.test.env` copied in and
  `npm install` run before investigation begins.
- Tests always run via `NODE_ENV=test npm test` (or `npm run test-single`),
  never ad-hoc `npx mocha` without `--exit --require ./tests/hooks.js` — see
  "Test invocation gotchas" in report-01 for why.
- Every report doc records: the claims as stated, verification against
  current source, verification against commit history (has this area been
  touched for security before, and did that prior work already address or
  miss this claim), a tradeoffs/design discussion, and an explicit decision
  log for any defaults chosen.
