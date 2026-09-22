# Advisory response pack — 2026-09

*Contributor-facing. Outgoing artifacts: each file says whether it has been sent.*

The pull requests and the responses to the five security advisories on
`nightscout/cgm-remote-monitor`. Current verdicts and what is still owed live in
[the disposition](../security-advisory-disposition-2026-09-21.md); this directory holds the text.

**State as of 2026-09-22.** All three PRs **merged into `dev` on 2026-09-21** (#8744, #8745, #8746;
`origin/dev` `74fc6619`) and are **not released** — `v15.0.8` (`origin/master` `92d08342`) is
still affected by GHSA-gjhc and GHSA-8849. The reporter replies and the metadata corrections are
**drafted and not sent**. No advisory is published.

## The five advisories at a glance

| advisory | verdict | v15.0.8 | what this pack contains | sent? |
|---|---|---|---|---|
| `GHSA-gjhc-pc29-r3m6` `loadRetro` | real, bypasses `denied` | **affected**; fix merged to `dev` (#8744) | PR 1 (sent), reply to the advisory, metadata + text | reply and metadata: **no** |
| `GHSA-8849-qjp5-vrrj` `/alarm` | real, bypasses `denied` | **affected**; fix merged to `dev` (#8745) | PR 2 (sent), reply to the reporter, metadata + text | reply and metadata: **no** |
| `GHSA-r3gv-x7fw-j2v5` operator injection | 1 of 3 PoCs stands; 1 is availability | `$where` affected (fix merged to `dev`, #8743); `$regex` affected, no fix | metadata + text corrections | **no** |
| `GHSA-mjp4-84fw-gj4v` v3 notes XSS | real, **fixed in 15.0.8** | not affected | metadata only | **no** |
| `GHSA-5mrq-gpqw-q5v5` websocket XSS | real, **fixed in 15.0.8** | not affected | metadata only — `critical` overstates it | **no** |

## Pull requests — record of what was sent

**Do not re-send.** These are the bodies as opened; each PR is merged.

| file | PR | branch | merged | merged head |
|---|---|---|---|---|
| [pr-1-loadretro.md](./pull-requests/pr-1-loadretro.md) | #8744 | `bf/ws-loadretro-auth` | 2026-09-21 | `9765e8cd` (as measured) |
| [pr-2-alarm-socket.md](./pull-requests/pr-2-alarm-socket.md) | #8745 | `bf/alarm-socket-scope` | 2026-09-21 | `a198e308` (measured `012f1623` + an integration merge of `dev`, not re-measured) |
| [pr-3-readable-warning.md](./pull-requests/pr-3-readable-warning.md) | #8746 | `bf/readable-warning` | 2026-09-21 | `91ed8d95` (measured `74731433` + an integration merge of `dev`, not re-measured) |

The `*.body.md` files are **byte-identical to the live PR bodies** (compared 2026-09-22 with
`gh pr view <n> -R nightscout/cgm-remote-monitor --json body`, ignoring trailing newline and CR;
no drift in either direction), and so carry no header of their own. The `## BODY` section of each
`pr-N-*.md` wrapper is identical to its `*.body.md`.

## Drafts not yet sent

| file | where it goes |
|---|---|
| [advisories/ghsa-gjhc-comment.md](./advisories/ghsa-gjhc-comment.md) | a comment on advisory GHSA-gjhc-pc29-r3m6 |
| [pull-requests/reply-to-reporter-ghsa-8849.md](./pull-requests/reply-to-reporter-ghsa-8849.md) | a comment on the reporter's PR #1 in the private advisory fork for GHSA-8849-qjp5-vrrj |
| [advisories/](./advisories/README.md) — one file per advisory | the metadata fields and the prose to add or replace, edited in the advisory UI |
| [advisories/apply-metadata.sh](./advisories/apply-metadata.sh) | sends the metadata patches — **dry run by default**, `--apply` to send; never publishes and never touches `state` |

## The through-line

Four of the five advisories argue from anonymous access. Nightscout ships
`AUTH_DEFAULT_ROLES=readable`, documents it as "readable by anyone who knows the URL", and warns
about it at every boot. **Anonymous read on a default install is the documented product, so the
question for each advisory is whether the access survives `AUTH_DEFAULT_ROLES=denied`** —
measured as a control first; `denied` does lock the REST surface down completely on both `dev`
and v15.0.8.

The two socket defects survive it. The others do not, or never depended on it. That single
distinction reorders the severities, strengthens two findings that were being understated,
corrects one that was being overstated, and explains why the reporter's own proposed fix for
`/alarm` does not work — it keys on `AUTHENTICATION_PROMPT_ON_LOAD` instead.

*See also*: [disposition](../security-advisory-disposition-2026-09-21.md) ·
[sequencing (snapshot)](../security-advisory-sequencing-2026-09-21.md) ·
[configuration matrix](../../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md) ·
[register](../nightscout-backfix-register.md)
