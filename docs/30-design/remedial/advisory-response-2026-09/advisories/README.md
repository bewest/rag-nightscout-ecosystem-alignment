# Responding to the five security notices — materials, 2026-09-21

All five are **drafts**. Nothing is published, nothing is in triage, no CVE is assigned.
`state` stays `draft` in every payload here; **publication is a separate, human action.**

## The one sequencing point that matters

The fixes are going out as **public PRs against `dev`**. A public PR that says
"alarm delivery went to the whole namespace" *is* the disclosure — it tells a reader what the
defect is and, from the diff, how to reach it. So the advisories should be **published at or
close to the moment those PRs go up**, not weeks later.

Publishing late is the worst of both: the defect is legible in a public diff while the advisory
that would tell operators *whether they are affected and what to do* is still hidden. The two PR
bodies are written to carry that information themselves — in particular that a default
`AUTH_DEFAULT_ROLES=readable` install has **zero** marginal exposure from either defect — so that
a reader who finds the PR before the advisory is not misled into panic or into a false sense of
safety.

## Files

| file | what |
|---|---|
| `ghsa-gjhc-loadretro.md` | metadata patch + revised text + the range correction |
| `ghsa-8849-alarm.md` | metadata patch + revised text + reporter credit |
| `ghsa-r3gv-injection.md` | metadata patch; the package name is wrong and one of three PoCs stands |
| `ghsa-mjp4-v3-notes-xss.md` | patched_versions is blank against a closed range; fix it |
| `ghsa-5mrq-websocket-xss.md` | severity `critical` overstates it; recommend `high` |
| `apply.sh` | dry-run-able `gh api` calls for every metadata patch above |
| `../prs/PR-3-reply-to-reporter.md` | the reply to the reporter's PR in the private fork |

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
