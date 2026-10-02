# The Nightscout ecosystem programme — one page for the whole

*Prepared for the Nightscout project; proposed for Nightscout Foundation stewardship. For the
foundation board, the maintainers of the ecosystem projects, and the community. **DRAFT PROPOSAL
for discussion.** Written 2026-09-29 against this repository at `37beb699` and cgm-remote-monitor
`official/dev` `7000eb18`. The parts on consent, research access, cross-border data and regulatory
terms need review by the foundation's counsel and a privacy or quality professional before any
decision rests on them (§9). Nothing here is decided.*

## 1. What this page is

Several pieces of work are under way or proposed across the Nightscout ecosystem: releases and
modernization of cgm-remote-monitor, shared schemas and conformance tests, multitenant hosting,
a research data commons, and new interfaces such as MCP. Each has its own document. This page
places them as **five layers of one programme** and says, for each layer, what exists, what is
proposed, and where it is decided.

It records no decisions and adds no work items. The order of the cgm-remote-monitor work is on the
[ROADMAP](ROADMAP.md); where it stands is on [PROGRAMME-STATUS](PROGRAMME-STATUS.md).

## 2. The picture

```
  shared, stewarded by the foundation                 built and run by each project
 ┌──────────────────────────────────────────────┐
 │ 5  Forward platform   MCP, agent-readable APIs │
 │ 4  Research and quality commons                │    Nightscout (cgm-remote-monitor)
 │ 3  Identity and trust                          │ ←→ Nocturne
 │ 2  Interoperability commons                    │    hosted operators
 └──────────────────────────────────────────────┘    other compatible servers
 1  Reference implementation: cgm-remote-monitor
                                                       Loop, Trio, AndroidAPS, xDrip+,
                                                       followers, reports, researchers
```

Layers 2–5 are assets that no single app, server or operator is placed to own, and that every one
of them uses. Layer 1 is one implementation, and it is listed separately because the other layers
are extracted from its behaviour: the schemas, the client census and the conformance tests are
measured against what cgm-remote-monitor and its clients actually do.

The principle: **the foundation stewards the shared layers and keeps them open to every
implementation; each implementation makes its own technical choices.** A second server, such as
Nocturne, is a second implementation of the same contract, not a competitor for the shared layers.
Stewarding a layer means hosting it and running its change process in public; the implementers
decide changes to it ([COLLABORATION-MODEL](COLLABORATION-MODEL.md) rule 5).

**One codebase, two uses.** The same open-source releases serve people who build and run their own
tools, under the digital rights in [DIGITAL-RIGHTS](../DIGITAL-RIGHTS.md), and companies that host
Nightscout or use its release evidence inside their own quality systems. Companies can pay for
assurance (packaged evidence, fixes on the line they run, test runs in their configuration), and
the evidence that decides each public release stays public (SQLite's model). Commercial offerings can
show they track the same contract with the same public conformance suite (CNCF's model). There is no
separate commercial edition. Neither use carries a clinical or regulatory claim for the other
(COLLABORATION-MODEL rules 6 and 8).

## 2a. Beneath the layers: devices and vendor clouds

The five layers rest on work that reaches the data in the first place: drivers that talk to CGMs and
pumps over Bluetooth and radio, often through pairing cryptography that volunteers had to work out,
and connectors that bring a person's data back out of vendor clouds. This is where data sovereignty
starts: the data holder's ability to get their own data, in a form they can compute on, and to hand
that job to tools and helpers they choose.

The [stack census of 2026-09-30](../60-research/programme/stack-census-2026-09-30.md) measured 63
repositories across these parts of the stack. 14 device protocols have 41 independent
implementations; six code bases log in to Dexcom Share and five to LibreLinkUp; and no device or
connector repository publishes a per-release test report. The
[quality-system proposal](QUALITY-SYSTEM.md) proposes a shared kit for every layer: vector corpora,
simulators, fixture suites, a change canary and one record shape. It also proposes how the
requirements for it would be agreed.

## 3. Layer 1 — the reference implementation

cgm-remote-monitor is the server most existing sites run, on MongoDB, with its own settings, data
and hosting. The work on it runs in three horizons ([PROGRAMME-STATUS](PROGRAMME-STATUS.md)):

- **Remedial.** Defects in what ships to operators today, tracked in the
  [backfix register](../30-design/remedial/nightscout-backfix-register.md). The 15.0.9 candidate is
  `3014f883`, not yet tagged ([ROADMAP §1](ROADMAP.md#1-the-next-release-1509)).
- **Modernization.** A staged release train for the dependency tree and runtime
  ([ROADMAP §2](ROADMAP.md#2-modernization-the-release-train)).
- **Multitenancy.** A second deployment target for hosting providers, on PostgreSQL. Self-hosted,
  single-tenant Nightscout on MongoDB stays first-class permanently (decisions D1 and D4,
  [execution plan](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)).

What bounds this layer is review capacity. In the generated table on PROGRAMME-STATUS (measured
2026-09-27), 138 of 172 queue items route review to the maintainer alone, and the SECURITY and SAFETY
reviewer rows mostly name no individual
([the two constraints](PROGRAMME-STATUS.md#the-two-constraints-neither-of-them-engineering)). The
[sponsored-team proposal](SPONSORED-TEAM-PROPOSAL.md) is the request that addresses this.

## 4. Layer 2 — the interoperability commons

The apps exchange data through the same collections (`entries`, `treatments`, `devicestatus`,
`profile`) without a shared, measured description of what goes in them. This repository builds
one ([collaboration start page](../60-research/collaboration/README.md)):

| asset | where | state |
|---|---|---|
| schemas, each field graded measured / declared / read-from-code | `specs/openapi/`, `specs/nsschema/`, `specs/jsonschema/generated/` | exists; measured over an 11-site corpus, 9 of them Loop |
| quirks registry | `specs/quirks/` | exists |
| per-client mappings with `file:line` citations | `mapping/<project>/` | exists |
| conformance assertions and replay vectors | `conformance/` | exists |
| client census: 40 client repositories against 15 parts of the API | [consumer impact](../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md) | exists, for 15.0.9 |
| controller descriptions (`decomposesTo`) | [proposal](../30-design/platform/PROPOSAL-controller-descriptions-2026-09-11.md) | proposed; adopted as the `devicestatus` direction by D11, not adopted by any controller project |
| hub-and-spoke adoption path | [adoption roadmap](../30-design/nightscout-adoption-roadmap-2026-09-11.md) | proposed ([ROADMAP §5](ROADMAP.md#5-proposals-not-yet-adopted)) |

With more than one server, this layer is what keeps client apps working on all of them. On
2026-09-23 Nocturne (`42275c81`) matched the 15.0.9 candidate on the count and filter fixes and
differed on eight measured behaviours; its own parity suite runs against Nightscout 15.0.3
([consumer impact §6](../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md#6-nocturne-parity)).
The model is the one WHATWG uses: several implementations, one living description, and one test
suite any of them can run ([sponsored-team proposal §6a](SPONSORED-TEAM-PROPOSAL.md#6a-more-than-one-server)).

## 5. Layer 3 — identity and trust

**What exists.** Identity today is per site. In cgm-remote-monitor, `API_SECRET` and tokens are
issued by each site. For the multitenant target, each tenant holds its own root credential (D13),
each tenant signs its own tokens (D14), and devices and the data path keep a native per-tenant
credential permanently (D17). Whether human identity comes from a shared Ory Kratos pool is held on a
proof (`T30-ORY-PROOF`, D17 row 2). Nocturne implements OAuth dynamic client registration (RFC 7591)
with a `software_id` per app and a bundled directory of known apps (Nocturne `42275c81`,
`KnownOAuthClients.cs`).

**What is proposed here.** Several parties need to recognise one another across sites: people,
self-hosted sites, hosting providers, researchers, the projects themselves, and organisations that
support the ecosystem. A **trust federation** would let each keep its own identity provider while
presenting verifiable claims ("this person is authenticated by organisation X; X is a recognised
participant; this service may read fields A and B for purpose P until date D"). The receiving
service decides whether the claims meet its own policy. The foundation would define what counts as
recognised participation. It would not hold anyone's passwords.

Existing standards cover most of the mechanism:

| standard | status | what it supplies |
|---|---|---|
| [OpenID Federation 1.0](https://openid.net/specs/openid-federation-1_0.html) | Final, 2026-02-17 | trust anchors, signed entity statements and trust chains for multilateral federations over OpenID Connect and OAuth 2.0 |
| [RFC 8693, OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html) | Standards Track, January 2020 | exchanging one token for another scoped to a downstream service, including delegation |
| [RFC 7591, Dynamic Client Registration](https://www.rfc-editor.org/rfc/rfc7591.html) | Standards Track | app self-registration with a `software_id`; Nocturne already uses it |
| [GA4GH Passport 1.2.1](https://ga4gh.github.io/data-security/ga4gh-passport) | current | signed "visas" carrying a researcher's affiliation, role, accepted terms and data-access grants between institutions |

**Where data may go.** Joining the federation does not mean data may cross every border. The
federation would carry identities, keys, schemas, capabilities, consent references and audit
identifiers (a shared control plane). Health data would stay in regional stores that apply their own
storage, processing and export rules (regional data planes). An approved analysis could run where the
data is and return only permitted aggregates. The European Health Data Space Regulation
([(EU) 2025/327](https://health.ec.europa.eu/ehealth-digital-health-and-care/european-health-data-space-regulation-ehds_en))
entered into force on 26 March 2025; its secondary-use rules begin applying to most data categories
in March 2029. Whether and how it applies to Nightscout data or to the foundation is a question for
counsel (§9).

**State.** No work item and no decision. The controller-descriptions proposal §2.2 already suggests
joining on Nocturne's reverse-DNS `software_id`, which would be a first shared identifier.

## 6. Layer 4 — the research and quality commons

**What exists.** `tools/ns2parquet/` turns Nightscout exports into parquet with the normalisation
written down. `tools/nsprobe` lets a data holder run this repository's probes on their own data
without sending it anywhere, and the [collaboration start page](../60-research/collaboration/README.md)
invites that. The OREF-INV-003 replication
([brief](../60-research/collaboration/oref-inv-003-replication-brief.md)) is the first external study
built on the pipeline. Release comparison already runs in this repository for cgm-remote-monitor:
the 15.0.9 candidate was soaked against 15.0.8 and replayed through a lab
([quality record](../60-research/programme/paving-the-cowpaths-2026-09-27.md)).

**What is proposed.** The [Nightscout datalake proposal](https://bewest.github.io/ns-data-proposal/)
asks the board for a 90-day pilot: a named foundation sponsor, a small advisory group, authority to
draft consent and access policies, work with hosting providers on consent brokering, monthly reports
and a go/no-go decision, at one of three budget levels. It treats the data lake as the first shared
service, not the whole programme. Its pilot outputs include a baseline data-quality report (gaps,
source coverage, drift), one conformance or release-comparison report, and governed extracts for two
or three external researchers.

This layer turns the others from one-off checks into a loop: consented data from many sites shows
whether a release changed behaviour, whether an uploader started writing malformed records, or
whether two implementations read the same field differently, and the findings return to layers 1
and 2 as test vectors and defects.

**Terms.** This page uses *post-deployment safety and quality monitoring*. It does not claim that
the foundation performs regulatory post-market surveillance (§9).

## 7. Layer 5 — the forward platform

**What exists.** The statistics API proposal specifies an MCP resource provider on top of a
documented statistics API (`REQ-STATS-005`,
[statistics API proposal](../sdqctl-proposals/statistics-api-proposal.md)). Nocturne ships an MCP
component. The report-statistics extraction on [ROADMAP §5](ROADMAP.md#5-proposals-not-yet-adopted)
is the step that makes those statistics a tested module with a documented API.

**What is proposed.** Agent-readable interfaces, and schemas for intent, action and evidence: what a
controller meant to do, what it did, and what it was based on. Controller descriptions (layer 2)
are the start of that.

**The boundary.** An interface that lets software read and explain data is a different thing from
one that takes part in a dosing decision. Anything on the dosing side needs the SAFETY reviewer that
the queue does not yet name, and depends on layers 2–4: typed schemas, identity and provenance, and
longitudinal quality data.

## 8. How the layers depend on each other

| layer | needs | makes possible |
|---|---|---|
| 1 reference implementation | reviewers and releases | the behaviour that layer 2 measures; the sites layer 4 draws on |
| 2 interoperability commons | layer 1's behaviour, client source code, real data | several servers and many clients working together |
| 3 identity and trust | layer 2's identifiers (`software_id`); D13–D17 for hosted sites | governed research access; hosted and self-hosted sites recognising one another |
| 4 research and quality commons | layer 3 for consent and access; layer 2 for normalised data | release comparison and quality signals across the ecosystem |
| 5 forward platform | layers 2–4 | agent and tool interfaces with provenance and a safety boundary |

## 9. The foundation's role, and points to decide

The two proposals already before the board each cover part of this page:

- the [sponsored-team proposal](SPONSORED-TEAM-PROPOSAL.md) is about people: review, compatibility
  and security work across layers 1 and 2;
- the [datalake proposal](https://bewest.github.io/ns-data-proposal/) is about the first shared
  service in layer 4.

This page adds the frame that joins them: layers 2–5 are shared infrastructure, stewarded by the
foundation and open to every implementation, and support for each implementation is a separate,
recorded decision.

**For the board:**

1. Which layers the foundation takes on as stewardship, and which it leaves to the projects.
2. How a proposal for any layer is submitted, reviewed and answered, and where decisions are
   published. [COLLABORATION-MODEL](COLLABORATION-MODEL.md) §5 proposes rules for this and for
   contributions, provider listings and disclosure, each borrowed from an organisation that uses
   it (Apache, CNCF, OpenStreetMap, OpenMRS, SQLite; §4 there).
3. Whether to take the datalake pilot and the sponsored team as separate decisions or as one
   programme with shared reporting, and whether the shared quality kit of the
   [quality-system proposal](QUALITY-SYSTEM.md) belongs in it.

**For the maintainers of the ecosystem projects:**

4. Whether the five layers are the right cut, and which shared assets are missing.
5. Whether the WHATWG pattern (one living description and shared tests) is acceptable to each
   server's maintainers, with contract changes through a recorded problem-report and change-request
   process like openEHR's ([COLLABORATION-MODEL](COLLABORATION-MODEL.md) §5, rule 5).

**For counsel, and for privacy and quality professionals:**

6. Whether the EHDS, GDPR or HIPAA apply to data a federation participant holds, and to the
   foundation as a party that defines participation without holding data.
7. What consent, de-identification and publication review a research extract needs, in each region
   that contributes data.
8. Whether *post-deployment safety and quality monitoring* avoids implying a regulated
   post-market role, and what the foundation must not claim.
9. Whether defining recognised participation in a federation creates any liability for the
   foundation.

**To verify before this page is quoted:** the standards' status and dates in §5 were read from their
publishers' pages on 2026-09-29. The datalake proposal's terms in §6 were read from its published
page the same day. The 138-of-172 figure in §3 is generated and changes with the queue; quote the
current table, not this page.
