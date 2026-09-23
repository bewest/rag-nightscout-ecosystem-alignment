# Responding to the five security advisories — materials

*Contributor-facing. Instructions for the person editing the advisories; the quoted blocks in each
file are the text to paste.*

**DRAFT — not sent.** As of 2026-09-22 all five advisories are drafts: nothing is published,
nothing is in triage, no CVE is assigned, and none of the metadata changes below has been applied.
`state` stays `draft` in every payload here; **publication is a separate, human action.**

## Timing

The fixes for GHSA-gjhc and GHSA-8849 merged into `dev` as public PRs on 2026-09-21 (#8744,
#8745) and are **not in a release**; v15.0.8 is still affected. A public PR is itself a
disclosure — it says what the defect is and, from the diff, how to reach it — so the defects are
now legible in public while the advisories that tell operators *whether they are affected and what
to do* are unpublished. The PR bodies carry that information themselves — in particular that a
default `AUTH_DEFAULT_ROLES=readable` install has **zero** marginal exposure from either defect —
so a reader who finds a PR first is not misled. Publish the advisories at or near the release that
carries the fixes, and leave `patched_versions` empty until then.

## Files

| file | what |
|---|---|
| [`ghsa-gjhc-loadretro.md`](./ghsa-gjhc-loadretro.md) | withheld until release |
| [`ghsa-gjhc-comment.md`](./ghsa-gjhc-comment.md) | withheld until release (draft, not sent) |
| [`ghsa-8849-alarm.md`](./ghsa-8849-alarm.md) | withheld until release |
| [`ghsa-r3gv-injection.md`](./ghsa-r3gv-injection.md) | withheld until release |
| [`ghsa-mjp4-v3-notes-xss.md`](./ghsa-mjp4-v3-notes-xss.md) | `patched_versions` is blank against a closed range; fix it |
| [`ghsa-5mrq-websocket-xss.md`](./ghsa-5mrq-websocket-xss.md) | severity `critical` overstates it; recommend `high` |
| [`apply-metadata.sh`](./apply-metadata.sh) | `gh api` calls for every metadata patch above — dry run unless `--apply`; never touches `state` |
| [`../pull-requests/reply-to-reporter-ghsa-8849.md`](../pull-requests/reply-to-reporter-ghsa-8849.md) | the reply to the GHSA-8849 reporter's PR in the private fork (draft, not sent) |

## Two corrections that apply across the set

**1. The npm coordinates reach nobody.** `nightscout` on npm stops at **14.2.11** (2022), so no
15.x range matches a published package, and `cgm-remote-monitor` — which GHSA-r3gv names — is not
an npm package at all. Self-hosters install from git or the `nightscout/cgm-remote-monitor` Docker
image. **Every advisory body should state the affected git tags and image tags in prose**, because
the ecosystem fields will not do it.

**2. Score the configuration, and say which one you scored.** Four of the five argue from
anonymous access. `AUTH_DEFAULT_ROLES` defaults to `readable`, `README.md:243` documents that as
"readable by anyone who knows the URL", and the app raises a persistent *"Nightscout readable by
world"* notice at boot. Anonymous read on a default install is the documented product. Every
severity below names the configuration it applies to.
