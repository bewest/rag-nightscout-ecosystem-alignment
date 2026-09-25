# Advisory response pack — 2026-09

*Contributor-facing. Outgoing artifacts: each file says whether it has been sent.*

The pull requests and the responses to the five security advisories on
`nightscout/cgm-remote-monitor`. What is still owed for each advisory is in queue items `ADV-*`
and `RT-0` in [`queue/work-queue.yaml`](../../../../queue/work-queue.yaml); this directory holds the
text.

**State as of 2026-09-23.** All three PRs **merged into `dev` on 2026-09-21** (#8744, #8745, #8746)
and are **not released**. The reporter replies and the metadata corrections are **drafted and not
sent**. No advisory is published.

**Details withheld (2026-09-23).** Three of the five advisories concern defects still present in
the shipping release, 15.0.8. Their write-ups in this pack, the disposition and sequencing records,
and the research notes are withheld until a release containing the fixes ships and the advisories
are published, matching the shortened descriptions of #8743, #8744 and #8745. The full text is in
git history at `ef376ecb` (the disposition and sequencing records were
`docs/30-design/remedial/security-advisory-{disposition,sequencing}-2026-09-21.md`).

## The five advisories at a glance

| advisory | v15.0.8 | what this pack contains | sent? |
|---|---|---|---|
| `GHSA-gjhc-pc29-r3m6` `loadRetro` | withheld until release | PR 1 (sent); reply and metadata withheld | reply and metadata: **no** |
| `GHSA-8849-qjp5-vrrj` `/alarm` | withheld until release | PR 2 (sent); reply and metadata withheld | reply and metadata: **no** |
| `GHSA-r3gv-x7fw-j2v5` operator injection | withheld until release | metadata withheld | **no** |
| `GHSA-mjp4-84fw-gj4v` v3 notes XSS | **fixed in 15.0.8**, not affected | metadata only | **no** |
| `GHSA-5mrq-gpqw-q5v5` websocket XSS | **fixed in 15.0.8**, not affected | metadata only — `critical` overstates it | **no** |

## Pull requests — record of what was sent

**Do not re-send.** These are the bodies as opened; each PR is merged.

| file | PR | branch | merged | merged head |
|---|---|---|---|---|
| [pr-1-loadretro.md](./pull-requests/pr-1-loadretro.md) | #8744 | `bf/ws-loadretro-auth` | 2026-09-21 | `9765e8cd` (as measured) |
| [pr-2-alarm-socket.md](./pull-requests/pr-2-alarm-socket.md) | #8745 | `bf/alarm-socket-scope` | 2026-09-21 | `a198e308` (measured `012f1623` + an integration merge of `dev`, not re-measured) |
| [pr-3-readable-warning.md](./pull-requests/pr-3-readable-warning.md) | #8746 | `bf/readable-warning` | 2026-09-21 | `91ed8d95` (measured `74731433` + an integration merge of `dev`, not re-measured) |

The `*.body.md` files are **byte-identical to the live PR bodies** (compared 2026-09-23 with
`gh pr view <n> -R nightscout/cgm-remote-monitor --json body`, ignoring trailing newline and CR;
no drift in either direction), and so carry no header of their own. #8744 and #8745 were shortened
on 2026-09-23 and their files follow; their `pr-N-*.md` wrappers are withheld stubs. The `## BODY`
section of `pr-3-readable-warning.md` is identical to its `*.body.md`.

## Drafts not yet sent

| file | where it goes |
|---|---|
| [advisories/ghsa-gjhc-comment.md](./advisories/ghsa-gjhc-comment.md) | a comment on advisory GHSA-gjhc-pc29-r3m6 |
| [pull-requests/reply-to-reporter-ghsa-8849.md](./pull-requests/reply-to-reporter-ghsa-8849.md) | a comment on the reporter's PR #1 in the private advisory fork for GHSA-8849-qjp5-vrrj |
| [advisories/](./advisories/README.md) — one file per advisory | the metadata fields and the prose to add or replace, edited in the advisory UI |
| [advisories/apply-metadata.sh](./advisories/apply-metadata.sh) | sends the metadata patches — **dry run by default**, `--apply` to send; never publishes and never touches `state` |

## Configuration matters

Nightscout ships `AUTH_DEFAULT_ROLES=readable`, documents it as "readable by anyone who knows the
URL", and warns about it at every boot, so anonymous read on a default install is the documented
product. Each advisory's severity names the configuration it was scored against.

*See also*: [configuration matrix](../../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md) ·
[register](../nightscout-backfix-register.md)
