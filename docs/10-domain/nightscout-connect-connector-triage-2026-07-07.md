# nightscout-connect Connector PR Triage (2026-07-07)

## Scope

This triage covers the `cgm-remote-monitor` dev candidate PR #8482 at `/home/bewest/src/worktrees/nightscout/cgm-pr-8447` and open `nightscout-connect` work for Dexcom Share, Glooko, and Nightscout source or output support.

## Local Worktrees

| Repository | Worktree | Branch | Notes |
|------------|----------|--------|-------|
| cgm-remote-monitor | `/home/bewest/src/worktrees/nightscout/cgm-pr-8447` | `candidates/inspect/dev` | PR #8482 head `17283fee`; local untracked `.nyc_output/` exists |
| nightscout-connect | `/home/bewest/src/worktrees/nightscout-connect` | `candidates/inspect/nightscout-connect` | Created from `origin/main` to avoid dirty `/home/bewest/src/nightscout-connect` checkout |

## cgm-remote-monitor PR #8482 Connector Impact

PR #8482 is a large dev branch staging the next cgm-remote-monitor release. GitHub reports 289 commits, 296 changed files, and green check runs across Node 20, 22, and 24 with MongoDB 4.4, 5, and 6. The PR is still merge-blocked at GitHub, but the connector-specific finding is narrower: it does not contain a `nightscout-connect` package bump.

`package.json` still depends on `nightscout-connect` `^0.0.12`, and `package-lock.json` still resolves `node_modules/nightscout-connect` to version `0.0.12`. See:

- `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/package.json:138`
- `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/package-lock.json:57`
- `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/package-lock.json:7375`

Release implication: Dexcom, Glooko, or Nightscout connector fixes must first land and publish in `nightscout-connect`, then cgm-remote-monitor needs a dependency bump before the candidate release can include those fixes.

## Dexcom Share

### Current Source Findings

The current `nightscout-connect` Dexcom Share adapter has several directly reproducible error-path problems:

- It returns the caught authentication error as a resolved value, which lets the state machine treat failed auth as success: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/dexcomshare.js:153`.
- It references `error.response.data` from catch blocks where the variable is named `err`: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/dexcomshare.js:169` and `/home/bewest/src/worktrees/nightscout-connect/lib/sources/dexcomshare.js:190`.
- It maps any truthy glucose payload, including non-array error shapes: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/dexcomshare.js:199`.

### PR Triage

| PR | Status | Triage | Reason |
|----|--------|--------|--------|
| nightscout-connect #55 | Open, clean merge state | Merge candidate | One-file patch, 34 additions and 12 deletions, normalizes `{accountId}`, rejects failed auth paths, guards catch blocks, and passes `node -c` syntax check |

Recommendation: merge PR #55 after review, then add follow-up tests for bare UUID and `{accountId}` auth shapes. This is the only connector fix found that looks narrow enough for a candidate release.

## Glooko

### Current Source Findings

The Glooko adapter currently logs in through JSON API `/api/v2/users/sign_in` and uses v2 pump plus CGM endpoints:

- Login endpoint: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/glooko/index.js:26`
- Device metadata shape: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/glooko/index.js:53`
- v2 reads: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/glooko/index.js:135` through `:139`
- Transform returns treatments only: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/glooko/index.js:167` and `:171`
- Fixed offset configuration: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/glooko/index.js:224` and `:232`

### Issue Triage

| Issue | Status | Triage |
|-------|--------|--------|
| #14 | Open, updated 2026-07-07 | Main tracking issue. Latest field report says EU JSON login is CSRF-blocked and web-form login works. |
| #38 | Open | Glooko can authenticate but returns zero treatments or readings. Latest comment points at `/v3/graph` investigation. |
| #10 | Open | Fixed timezone offset does not handle DST. Should become named time zone support. |
| #9 | Open | Current main appears to have a null guard for `last_known`; candidate for close after confirming release version. |
| #44 | Open | Configuration or docs issue: output Nightscout URL was undefined. Needs README and validation cleanup, not a connector engine rewrite. |
| #45 | Open | Feature request for more Omnipod 5 data from Glooko. Depends on solving reliable Glooko auth and data extraction first. |

### PR Triage

| PR | Status | Triage | Reason |
|----|--------|--------|--------|
| #31 | Open, clean merge state | Partial, not sufficient | Adds richer `deviceInformation`, but latest #14 analysis says root cause is CSRF on JSON login. |
| #46 | Open, clean merge state | Defer | Refactor plus Glooko changes across three files without tests. Too broad for release stabilization. |
| #51 | Open, dirty merge state | Do not merge as-is | Adds Puppeteer and has known timestamp problems; includes `deploy.sh`; useful as a research artifact. |
| #49 | Closed | Reference only | Narrow fetcher cleanup, manually tested, but superseded by broader auth/API drift. |
| #50 | Closed | Reference only | Useful testing/client extraction direction: Mocha tests and isolated Glooko API client. |

Recommendation: do not block the cgm-remote-monitor candidate release on Glooko. Open a new focused PR that implements web-form CSRF login, regional host handling, v3 graph fallback, named time zones, and fixtures. Use #50's testability pattern rather than #51's Puppeteer path unless no lower-risk web-login implementation is viable.

## Nightscout Source and Output

### Current Source Findings

The Nightscout source uses v1 entries reads with v2 token acquisition:

- Verify auth: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/nightscout.js:40`
- Authorization subjects: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/nightscout.js:55`
- Token request: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/nightscout.js:92`
- v1 entries read: `/home/bewest/src/worktrees/nightscout-connect/lib/sources/nightscout.js:132` and `:133`

The Nightscout output still posts v1 entries and treatments:

- Entries output: `/home/bewest/src/worktrees/nightscout-connect/lib/outputs/nightscout.js:35`
- Treatments output: `/home/bewest/src/worktrees/nightscout-connect/lib/outputs/nightscout.js:48`

### PR Triage

| PR | Status | Triage | Reason |
|----|--------|--------|--------|
| #52 | Open, clean merge state | Defer and split | 26 files, 2,403 additions, Docker/docs/compat changes, source and output changes together, and a comment reporting `register_loop` crashes. |

Recommendation: split Nightscout v3 work into small PRs: v3 read client, v3 output client, loop registration tests, then migration docs. Do not include PR #52 in a release candidate without that split.

## Release Decision Summary

| Area | Candidate Release Action | Follow-Up |
|------|--------------------------|-----------|
| cgm-remote-monitor PR #8482 | Continue release review, but treat third-party connector fixes as dependency follow-up unless `nightscout-connect` publishes a new version first | Bump package after connector release |
| Dexcom Share | Merge #55, publish patch release if review passes | Add mocked response tests |
| Glooko | Defer existing PRs from release | Create new focused web-login plus v3 graph PR |
| Nightscout source/output | Defer #52 from release | Split v3 support into testable increments |

## New Traceability

- GAP-CONNECT-013, REQ-CONNECT-013: Dexcom Share auth failure propagation
- GAP-CONNECT-014, REQ-CONNECT-014: Glooko EU authentication and timestamp handling
- GAP-CONNECT-015, REQ-CONNECT-015: Nightscout v3 source and output parity
