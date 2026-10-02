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

# Review packet — DEPENDABOT-CONFIG

**Dependabot runs with no configuration: security PRs target master, and alerts
count fixes that are on dev**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@50bc1084` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=DEPENDABOT-CONFIG` is the measurement |
| semver | `n/a` |

## What this changes

.github/dependabot.yml (new) and repository settings; no product code.

## Why that semver

repository configuration

## Who should review this, and why

maintainer

## What was measured

**`sh -c '! git -C externals/cgm-remote-monitor-official cat-file -e origin/dev:.github/dependabot.yml'`** &nbsp;·&nbsp; kind: `static`

PASSES while dev has no .github/dependabot.yml (measured 2026-10-01); it goes
red once a configuration is added, at which point this item is done or
replaced by a gate on its contents.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured 2026-10-01 with gh api: Dependabot security updates enabled, no
  dependabot.yml on dev or master, default branch master. Of the Dependabot
  PRs: 45 closed unmerged and 1 merged against master, 21 merged and 1
  closed against dev, 2 open against master (#8787, #8789). 85 open alerts,
  all measured against master (15.0.8): 61 in runtime scope and 23 in
  development scope by Dependabot's own classification, which records where
  a package is declared, not whether its vulnerable code is reached.

## Evidence

- [`releases/cgm-remote-monitor-15.0.9/contents.md`](../../releases/cgm-remote-monitor-15.0.9/contents.md)

## Notes carried on the item

Raised by the maintainer 2026-10-01 ("I wonder if dependabot is configured
correctly; it produces a lot of noise that gets taken out of context").
Options, none decided: (1) a dependabot.yml with version updates targeting
dev, grouped, on a schedule, so routine bumps arrive where work happens; (2)
keep alerts, and dismiss each one that is fixed on dev or not reachable, with
GitHub's dismissal reason and a comment linking the triage, so the alert list
shows the project's assessment; (3) release more often, since alerts close
only when master moves. Security-update PRs follow the default branch and
dependabot.yml's target-branch does not change that, so turning them off and
relying on (1) and (2) is the way to stop PRs against master.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=DEPENDABOT-CONFIG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
