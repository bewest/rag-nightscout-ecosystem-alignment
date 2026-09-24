# Working with us: a start page for researchers and their agents

**Status:** living document, revised 2026-09-24.

This is the page to send a researcher who holds Nightscout or OpenAPS data, builds tools on
it, or works with coding agents, and who might bring that effort to the alignment work here.
It says what the work is, what help changes it, and where each kind of contribution starts.

Nothing here evaluates anyone's therapy, and nothing here is medical advice. The work is
about how diabetes data is written, stored and read across the Nightscout ecosystem.

## What this repository is for

The Nightscout ecosystem is many independent programs: uploaders (AndroidAPS, Trio, Loop,
xDrip, bridges), the Nightscout server, and readers (followers, reports, research tools).
They exchange data through the same collections (`entries`, `treatments`, `devicestatus`,
`profile`, `activity`) without a shared, measured description of what goes in them. This
repository builds that description and checks it against real data and real source code:

| Artefact | Where | What it is |
|---|---|---|
| Schemas | `specs/openapi/`, `specs/nsschema/`, `specs/jsonschema/generated/` | per-collection field definitions, each field graded measured / declared / read-from-code |
| Quirks registry | `specs/quirks/` | measured deviations from the schema, with prevalence and reader guidance |
| Mappings | `mapping/<project>/` | how each client writes and reads each field, with `file:line` citations |
| Conformance | `conformance/` | assertions and replay vectors, including oref0 and AAPS algorithm runners |
| Data pipeline | `tools/ns2parquet/` | Nightscout to parquet, with the normalisation heuristics written down |
| Research | `tools/oref_inv_003_replication/`, `docs/60-research/` | analysis built on the pipeline |

The measurement behind the schemas and its limits:
[`nightscout-typed-schema-evidence-2026-09-10.md`](../../30-design/platform/nightscout-typed-schema-evidence-2026-09-10.md).
The short version: 11 sites, 9 of them Loop, fetched through API v1 only. Most of what an
AndroidAPS, Trio or OpenAPS user writes has been read from source code but never measured.

## Four ways in

Pick the ones that fit. None requires the others.

### 1. Run our probes on your data

For anyone holding raw Nightscout exports or a flattened warehouse. Your data stays on your
machine; aggregate counts come back if you choose to send them.

- Brief: [`external-data-validation-brief.md`](external-data-validation-brief.md)
- For your coding agent: [`tools/nsprobe/AGENTS.md`](../../../tools/nsprobe/AGENTS.md)
- The 18 questions it answers: [`tools/nsprobe/questions.yaml`](../../../tools/nsprobe/questions.yaml)

### 2. Take a research question further

Analysis here has reached the limit of an 11 to 31 patient cohort. The open questions a larger
or different cohort could settle are listed with the claim each one tests.

- OREF-INV-003 replication and the 18-feature algorithm-neutral set:
  [`oref-inv-003-replication-brief.md`](oref-inv-003-replication-brief.md)
- Schema questions Q00 to Q17 above, and their Track C analysis tasks.

### 3. Build on the schemas, or tell us where they are wrong

For authors of uploaders, readers and research tools. If your tool reads Nightscout, the
mapping docs and the quirks registry say what you will actually receive; if your tool writes
it, the schemas say what readers expect.

- Find your client under `mapping/`, or start one from `mapping/_template.md`.
- A field your tool relies on that the schema gets wrong, or does not have: open an issue
  naming the collection, the field path, and the client that writes it. Source references
  are enough; no data needed.
- Replay and simulation tools (such as oref-digital-twin) need inputs no uploader records
  today; see
  [`PROPOSAL-replay-fidelity-changes-2026-09-11.md`](../../30-design/platform/PROPOSAL-replay-fidelity-changes-2026-09-11.md).

### 4. Review

Most work here has had no human reviewer. If you can read Nightscout code or data analysis
critically, that is the scarcest contribution:
[`docs/00-overview/REVIEWER-ONBOARDING.md`](../../00-overview/REVIEWER-ONBOARDING.md).

## Rules for people and agents working here

This repository is public. Every commit, issue and pull request is published.

1. **No personal data, ever.** No CGM traces, treatments, profiles, device logs, site URLs,
   names, emails, tokens or API secrets in any file, commit message, issue or pull request.
   Aggregates only, with site or user counts of at least 3 behind any named value (the rule
   `tools/nsprobe/privacy.py` enforces).
2. **Secrets come from the environment**, never from a file in the repository.
3. **Say how you know.** A claim is either measured (name the data and the command that
   produced the number) or read from code (name the file and line). Label which.
4. **Numbers carry an anchor**: the date and commit they were produced at, or the command that
   reproduces them.
5. **Clinical content is framed as data, not advice.** Findings describe what data shows about
   how software behaves, never what a person should set.

For coding agents: the nsprobe [`AGENTS.md`](../../../tools/nsprobe/AGENTS.md) is the most
complete statement of these rules as instructions, and applies beyond that tool.

## Contact

Ben West, maintainer, through issues on this repository (no data in them), or ask there for a
private channel.
