# Nightscout ecosystem alignment

*Contributor- and reviewer-facing.* This site is built from the repository
[`bewest/rag-nightscout-ecosystem-alignment`](https://github.com/bewest/rag-nightscout-ecosystem-alignment),
branch `@@BRANCH@@`, commit
[`@@SOURCE_SHA@@`](https://github.com/bewest/rag-nightscout-ecosystem-alignment/commit/@@SOURCE_SHA_FULL@@)
(@@SOURCE_DATE@@).

## What this workspace is

A quality-control workspace for the Nightscout-compatible ecosystem. It holds
tooling, documentation, evidence and QC harnesses for working across Nightscout,
AAPS, Loop, Trio and the other projects that exchange data with a Nightscout
server. The shipping server, `cgm-remote-monitor`, is a separate repository;
findings are written up here and referenced from there. The upstream projects
are checked out side by side under `externals/`, pinned in
`workspace.lock.json`; they are not part of this site, and links into them go
to the upstream repository at the pinned commit.

## How it is organised

| section | what it holds |
|---|---|
| [Overview](docs/00-overview/) | the programme as a whole: mission, programme status, roadmap, the items waiting on a person, and the proposals |
| [Releases](releases/README.md) | tag messages, release notes and contents records for releases of `cgm-remote-monitor` and `nightscout-connect` |
| [Queue](queue/README.md) | one work queue for every programme, with the gates each item is checked by |
| [Research](docs/60-research/) | experiment reports, analyses and measurement records |
| [Design](docs/30-design/) | design documents by programme: remedial, modernization, tenancy and platform |
| [Pages](site/pages/README.md) | committed rich pages, such as the [programme page](site/pages/nightscout-ecosystem-programme.html) |

The tabs above follow the repository's folder layout; folders with few pages sit
under **More**.

## Where to start

- [Reviewer onboarding](docs/00-overview/REVIEWER-ONBOARDING.md): read this
  first if you are considering reviewing work here.
- [The Nightscout ecosystem programme](site/pages/nightscout-ecosystem-programme.html):
  the pieces of work across the ecosystem, placed as five layers of one
  programme.
- [How 15.0.9 was made](site/pages/cgm-remote-monitor-15.0.9-colophon.html): the
  release cycle's figures, with charts of merges, defects found and closed,
  test runs and the regressions caught before release.

## Record or Living

Every page carries one of two labels under its title.

- **Record**: a point-in-time document, such as a dated report or a test
  result. It is not kept up to date; the label gives the date it records.
- **Living**: any other page. The label gives the date and commit of its last
  change.

## What is not published here

Some material in the repository is deliberately left off this site:
security-sensitive material about defects still live in a shipping release,
per-person health data, data held under a data holder's consent, and drafts of
messages or pull requests that have not been sent. Links to such material
appear as "(not published)".

Participant IDs from research data commons are replaced by pseudonyms when the
site is built.
