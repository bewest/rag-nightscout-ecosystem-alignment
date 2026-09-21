# Advisory response pack — 2026-09-21

Everything needed to open the pull requests and answer the five security notices. Assembled so
that somebody other than its author can execute it.

**Vehicle: `dev`.** Decided 2026-09-21. The PRs are ordinary public PRs against
`nightscout/cgm-remote-monitor`. See §0 of
[the sequencing record](../security-advisory-sequencing-2026-09-21.md) for what that implies
about timing — chiefly that **the advisories should publish at or near the moment the PRs go
up**, and that **this repository should be pushed after the PRs, not before**, because it is
public and currently holds the fullest description of both defects anywhere.

## The five notices at a glance

| advisory | verdict | ships on v15.0.8 today? | what this pack contains |
|---|---|---|---|
| `GHSA-gjhc-pc29-r3m6` `loadRetro` | real, bypasses `denied` | **yes, unfixed** | PR 1 + metadata + text |
| `GHSA-8849-qjp5-vrrj` `/alarm` | real, bypasses `denied` | **yes, unfixed** | PR 2 + metadata + text + reply to the reporter |
| `GHSA-r3gv-x7fw-j2v5` operator injection | 1 of 3 PoCs stands | `$where` yes | metadata + substantial text corrections |
| `GHSA-mjp4-84fw-gj4v` v3 notes XSS | real, **already fixed** | no | metadata only |
| `GHSA-5mrq-gpqw-q5v5` websocket XSS | real, **already fixed** | no | metadata only — `critical` overstates it |

## Pull requests

| file | branch | base | commit |
|---|---|---|---|
| [pr-1-loadretro.md](./pull-requests/pr-1-loadretro.md) | `bf/ws-loadretro-auth` | `dev` | `9765e8cd` |
| [pr-2-alarm-socket.md](./pull-requests/pr-2-alarm-socket.md) | `bf/alarm-socket-scope` | `dev` | `012f1623` |
| [reply-to-reporter-ghsa-8849.md](./pull-requests/reply-to-reporter-ghsa-8849.md) | — | — | a comment on PR #1 in the private fork |

Each PR file carries the `gh pr create` invocation at the top and the body below a `## BODY`
marker. The branches are **local and unpushed**; a human pushes them. They are based on
`origin/dev` `59430336`, touch disjoint files, and `git merge-tree` reports them clean against
each other, so they can be reviewed and merged in either order.

A third PR — the `readable`-by-world boot warning, register BF-77 — is in preparation on
`bf/readable-warning`; it is an ordinary defect fix with no disclosure dimension.

## Advisories

[advisories/README.md](./advisories/README.md) explains the two corrections that apply across
the whole set: the npm coordinates reach nobody (the package tops out at 14.2.11 from 2022, and
one advisory names a package that does not exist), and every severity should name the
configuration it scores.

One file per advisory, each giving the exact field changes in a table and the exact prose to
add or replace. [`apply-metadata.sh`](./advisories/apply-metadata.sh) sends the metadata patches
— **dry run by default**, `--apply` to send. It never publishes and never touches `state`; the
prose rewrites are deliberately left to the web UI where the rendering is visible.

## The through-line, if you read nothing else

Four of the five advisories argue from anonymous access. Nightscout ships
`AUTH_DEFAULT_ROLES=readable`, documents it as "readable by anyone who knows the URL", and warns
about it at every boot. **Anonymous read on a default install is the documented product, so the
question for each notice is whether the access survives `AUTH_DEFAULT_ROLES=denied`** — measured
as a control first, and it does lock the REST surface down completely on both `dev` and v15.0.8.

The two socket defects survive it. The others do not, or never depended on it. That single
distinction reorders the severities, rescues two findings that were being understated, corrects
one that was being overstated, and explains why the reporter's own proposed fix for `/alarm`
does not work — it keys on `AUTHENTICATION_PROMPT_ON_LOAD` instead.

*See also*: [disposition](../security-advisory-disposition-2026-09-21.md) ·
[sequencing](../security-advisory-sequencing-2026-09-21.md) ·
[configuration matrix](../../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md) ·
[register](../nightscout-backfix-register.md)
