# Partner readiness: agreeing terms with a device manufacturer

*What this is: a proposal (part 3 of the overview, recommendations; [how the overview is organised](README.md)), for the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community. Read after the [quality system](QUALITY-SYSTEM.md); leads to [why organise](WHY-ORGANISE.md). **DRAFT PROPOSAL for discussion.** Written 2026-10-16 against this repository at `faafc57c`. The
facts it relies on are on the [governance](observations/GOVERNANCE-TODAY.md) and
[evidence](observations/ECOSYSTEM-EVIDENCE.md) pages. It touches contracts, intellectual property,
medical-device reporting, privacy and competition law. Each of those parts needs review by the
foundation's counsel, and the reporting parts by a regulatory or quality professional, before any
decision or negotiation rests on them (§10). Nothing here is decided.*

*Author's interests: the author maintains cgm-remote-monitor, founded a company that hosts
Nightscout commercially, and could be a candidate for paid work under the related proposals. The
[collaboration rules](COLLABORATION-MODEL.md) §5 would apply to that company and to the author like
anyone else.*

## 1. The request

Prepare the ecosystem to make written agreements with pump and CGM manufacturers for access to
their devices and data, starting with read-only access, and build the shared operations a
manufacturer will ask about before it signs: one named accountable party per agreement, security
response, and complaint and incident handling.

Today, access to most devices rests on protocols that volunteers worked out, and on the
interoperability rights described in [DIGITAL-RIGHTS](../DIGITAL-RIGHTS.md). Those rights remain.
Where a device accepts commands only from a client holding a credential the manufacturer issues,
knowing the protocol is no longer enough: access then depends on an authorised relationship with the
manufacturer. This page is about being ready for that relationship.

### What is at stake on each path

Encryption alone does not close a path. Tandem's t:slim X2 and Mobi pair with a code shown on the
pump, and open implementations work with them
([device-layer census](../60-research/programme/stack-census-2026-09-30/device-layer.md); pumpX2
`6fa9459`). Dexcom G7 and Libre 3 also check the app: after the person's code or NFC scan, the
sensor asks for a client credential, and the open implementations work by carrying a fixed one
that the manufacturer did not issue to them, in their source or as a separate download
(xdripswift `c268542`, Juggluco `75399d7`, LibreLoop `150d2b1`, read 2026-10-17). That access lasts while new sensors and firmware keep accepting it. A path closes when a
device stops accepting every credential open software can present, or when the data is sealed so
that the phone cannot read it.

| path | what it feeds | what would close it | what happens when it closes |
|---|---|---|---|
| sensor to phone, over the device's own radio link | the glucose input of an automated insulin delivery (AID) app; readers such as xDrip+ | a sensor that stops accepting the client credential open apps present, or pairs only with an app the manufacturer has authenticated; readings encrypted end to end for the vendor's cloud, so the phone relays data it cannot read | automation stops. In Loop, no new dose is recommended once the newest reading is more than 15 minutes old, and the temporary basal rates Loop sets last at most 30 minutes, after which the pump returns to its programmed schedule (LoopAlgorithm `7d016fb`, `inputDataRecencyInterval`, `tempBasalDuration`). Other controllers: not verified here (§10) |
| phone to pump, commands | automated and manual dosing from the open app | a pump that accepts commands only with a credential the manufacturer issues | the pump keeps running its own programmed delivery; automation and dosing from the open app stop, and the person needs the manufacturer's own controller for that pump |
| vendor cloud to a connector | Nightscout sites, and the caregivers who follow them | login, bot-defence or terms changes, or a cloud that admits only approved apps | readings stop arriving at the site until a connector fix ships ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)); remote following and alerts through the site stop. The loop on the phone is not affected |
| device generations in supply | which devices people can obtain | today's accessible devices leaving sale or insurance coverage | people move to newer devices, whose paths may be closed. No end-of-sale dates have been collected (§10) |
| build and signing platform | every self-built app | signing and declaration policy (Apple, Google) | the app stops running when its certificate or build expires ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)) |

How many people each closure would reach is not counted anywhere today (§6).

The paths are drawn as believed, today and emerging in
[1·access-paths](perspective/PROCESS-MODELS.md#1access-paths-who-holds-the-key-on-each-path),
with a ladder of how much each device makes an open app depend on its manufacturer. Device by
device:

![1·access-matrix: for each pump and CGM line, the device link, the number of open implementations, the vendor-cloud route connectors use, the manufacturer's route for outsiders, the real-time route for outsiders, and supply. Pump links are mostly open (step A); Dexcom G7, Libre 3, MiniMed 780G and Omnipod 5 check the app (step D), met today by credentials not issued to the open implementations; Eversense 365 needs a certificate fetched through the person's own account (step C); SmartGuide advanced security is not determined. Cloud routes exist for Dexcom, Libre, CareLink and Tandem Source, at the vendor's discretion. The only route for outsiders is Dexcom's API with a one-to-three-hour delay; every real-time route is by invitation or not published. Supply has not been collected for any device](perspective/diagrams/1-access-matrix.svg)

The cells that read "not checked", "not read" or "not collected" are the list of what to find out
next (§10).

**Keeping access has running costs, with or without an agreement.** Without one, connectors follow
each vendor-cloud change ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)),
the US copyright exemption for device data needs evidence at each three-yearly renewal
([vendor note §3.4](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#34-dmca-1201-exemptions-37-cfr-20140)),
and each new phone operating system needs app releases. With one, continued access depends on the
terms in §4, which are the ecosystem's requests. Nothing in this repository yet shows what would
lead a manufacturer to accept them.

## 2. Three tiers of access, and which to ask for first

The tiers are this page's terms for technical risk. They are not FDA classifications.

| tier | what the integration may do | relative risk |
|---|---|---|
| **A — observe and export** | read glucose, device status, delivery history and alarms; export them. The agreement states the path (the device's own radio link, or the vendor's cloud) and the maximum delay | lowest |
| **B — configure and coordinate** | limited, confirmed settings changes, with an audit trail and device-specific limits | higher |
| **C — control insulin delivery** | authenticated dosing or delivery commands | highest; needs device-specific validation and a regulatory pathway |

**Recommendation: ask for tier A first, and separately.** Tier A is the data-rights agreement. It
delivers the five rights in the [data rights primer](../10-domain/data-rights-primer.md) — access,
export, share, delegate, audit — for one device line, and it does not wait on anyone obtaining
permission for a closed loop. Tiers B and C can follow under the same framework, each as its own
agreement.

**What tier A protects depends on its path and delay.** An AID app needs readings on the phone
within minutes (Loop stops recommending at 15, §1). A tier A agreement for a delayed cloud feed,
such as Dexcom's public API, which runs one hour behind in the US and three elsewhere
([vendor note §1.2](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#12-dexcom)),
secures display, export, sharing and research. It does not secure automated insulin delivery. For
that, tier A has to cover real-time reads over the device's own link, and the pump side needs
tier C.

The same relationship at each tier, drawn ([idea·tiers](perspective/STRUCTURES.md#ideatiers)):

![Tier A: the manufacturer's agreement gives the integration read access; the device line reports glucose, status, history and alarms to the client app; readiness evidence goes back](perspective/diagrams/idea-tiers--a.svg)

![Tier B: the agreement adds limited, confirmed settings changes from the app to the device, with an audit trail back to the manufacturer](perspective/diagrams/idea-tiers--b.svg)

![Tier C: the agreement adds authenticated dosing and delivery commands, with device validation, a regulatory pathway, and validation and complaints back to the manufacturer](perspective/diagrams/idea-tiers--c.svg)

## 3. What a manufacturer will need to see

A manufacturer weighs whether a relationship creates technical, security, legal, regulatory and
business risk it can manage. These are the questions it is likely to ask, and the evidence that
exists in the ecosystem today.

| question | evidence a manufacturer would expect | what exists today |
|---|---|---|
| Who is accountable? | a legal entity, named officers, named technical and security contacts | the foundation is a 501(c)(3) ([governance §3](observations/GOVERNANCE-TODAY.md#3-the-nightscout-foundation)); no named security contact for any project |
| Is the software trustworthy? | versioned specifications, independent review, reproducible test results tied to a release | schemas, mappings and conformance assertions for the server API ([programme §4](ECOSYSTEM-PROGRAMME.md#4-commons-a--the-shared-contract)); no device or connector repository publishes a per-release test report ([evidence §1](observations/ECOSYSTEM-EVIDENCE.md#1-what-the-ecosystem-consists-of)) |
| Can a security problem be contained? | a disclosure policy, a response plan, the ability to revoke a client's access | none of the 20 repositories measured has a SECURITY policy of its own; private vulnerability reporting is on in 4 of them ([governance §2](observations/GOVERNANCE-TODAY.md#2-written-project-governance)) |
| Will defects that reach users be handled? | a complaint workflow, investigation records, an escalation route to the manufacturer | a defect register for cgm-remote-monitor ([backfix register](../30-design/remedial/nightscout-backfix-register.md)); no complaint workflow in any project (§6) |
| How are releases controlled? | signed builds, recorded change review, a software bill of materials (SBOM), release provenance | review rules differ by repository ([governance §1](observations/GOVERNANCE-TODAY.md#1-who-decides-in-each-project)); no SBOM or build-provenance record found in this repository's survey |
| Is personal data protected? | access controls, a privacy policy, retention rules, audit logs | per site; no ecosystem privacy or retention policy |
| Will the counterpart still be there? | funding, insurance, succession, continuity and termination terms | concentration measured in [evidence §4](observations/ECOSYSTEM-EVIDENCE.md#4-where-the-maintenance-time-goes-today); the rest is in [what only the foundation can supply](observations/GOVERNANCE-TODAY.md#7-what-only-the-foundation-can-supply) |
| Who bears which liability? | an allocation in the contract, stated intended uses, insurance matched to the role | none |
| What does the manufacturer gain? | fewer unsupported integrations, structured reports of field failures, evidence about third-party use | proposed in §6; not yet operating |

Most rows in the last column say "none". That is the finding this page is built on: the
engineering evidence is ahead of the operational evidence.

The proposition to a manufacturer changes with it. Not "allow our applications to connect to your
devices", but: *the ecosystem runs shared verification, security response and incident handling for
independent applications, which lowers the cost and risk of supporting the third-party use that
already happens, and shows what that use looks like.*

## 4. What the ecosystem needs from an agreement

§3 is what the manufacturer needs from us. An agreement also has to secure what people with
diabetes and the projects need from the manufacturer. These terms carry the data rights.

| term | why it matters |
|---|---|
| **Nonexclusive access** | any implementation that meets the published criteria may qualify; sponsorship or first arrival buys no right to exclude others (the principle of [COLLABORATION-MODEL](COLLABORATION-MODEL.md) rule 2, "money and staff buy work, not control") |
| **Patient-directed and portable** | the person decides which tools and helpers receive their data, and can take it with them; delegation to caregivers and clinicians is included |
| **Notice before change** | a stated notice period for firmware, API, cloud and certificate changes that affect the integration, and test devices or a sandbox to try them |
| **Revocation by process** | a client's access is suspended or revoked under published grounds with notice and appeal, except an immediate suspension for an active security incident; revoking a credential must leave a person's devices in a defined safe state |
| **Freedom to publish results** | conformance and interoperability results can be published, so other implementers and users can see what works |
| **Stated costs and limits** | any fees, rate limits and support channels are written into the agreement, not set later |

## 5. Terms of the agreement itself

| term | what to settle |
|---|---|
| **Intellectual property and licences** | whether a protocol specification shared under a non-disclosure agreement can be implemented in source code published under the projects' licences (AGPL, GPL, MIT and BSD are all in use, [governance §1](observations/GOVERNANCE-TODAY.md#1-who-decides-in-each-project)); if not, which parts stay closed and who holds them. This is the term most likely to block an agreement. |
| **Regulatory roles** | who is the manufacturer for which function, and which claims each party may make |
| **Intended use and labelling** | what each tier's integration may say it does, and use of each party's name and marks |
| **Complaints in both directions** | what each party forwards to the other, within what time, and through which contact (§6) |
| **Data and jurisdiction** | which privacy regimes apply to the data each party handles, by region |
| **Termination and wind-down** | how people already using the integration keep working, or are moved safely, when an agreement ends |
| **Disputes, and competition** | how disagreements are resolved; a competition-law review of any exclusivity or selection criteria |

## 6. Complaint, incident and support handling

**Why it comes first.** A manufacturer subject to FDA's quality-system rule must keep records of
complaints about its device, and must report some events to FDA: certain deaths, serious injuries
and malfunctions within 30 calendar days of becoming aware of them, and some within five work days
(21 CFR Part 803). Reports that arise through third-party software are part of that duty. A partner
with no channel to receive and forward them is a source of events the manufacturer cannot see.
Expect any agreement to ask for one.

**Three streams, one intake.** Reports arrive today on Discord, Facebook, Zulip, Gitter and GitHub
([governance §2](observations/GOVERNANCE-TODAY.md#2-written-project-governance)). A shared intake
can accept all of them, but triage separates three kinds:

| stream | example | handling |
|---|---|---|
| support | how to set up a connector | answered in the community's channels; no safety record |
| complaint | a stale glucose value shown as current; displayed delivery differs from the pump's record | a record with an owner, investigation and disposition |
| security vulnerability | a flaw that exposes data or allows unauthorised commands | under embargo until fixed; through private vulnerability reporting |

**The lifecycle of a complaint.** Received → triaged for severity, safety, security and the devices
involved → investigated (reproduce, logs, root cause, fix, test) → reviewed for referral to the
responsible manufacturer, and for containment → closed with corrective action, a regression test,
an answer to the reporter, and a place in the trend data. Each record keeps the time received, the
software and device versions, the owner, the suspected safety effect, the investigation history,
each referral decision, and the reason for closing. It also records when the party handling it is
**not** the manufacturer of the device involved.

**Intake is not legal responsibility.** A shared intake coordinates investigation and routes reports
to the party that is legally responsible. It does not take over a manufacturer's quality system, and
it does not by itself give every project the duties of a manufacturer. Whether operating it creates
any duty for the foundation is a question for counsel (§9, question 7). Anyone can also report a
device problem directly to FDA through MedWatch.

![Complaints in both directions: a person reports to the shared intake and gets an answer; the intake sends linked reports and a regression test to projects and gets fixes back; it refers reportable events to the manufacturer, which forwards what the agreement says and reports some events to the regulator; the person can also report to the regulator directly](perspective/diagrams/idea-complaints.svg)

**What the records are for.**

- **Across projects.** A firmware change that breaks one CGM's link in Nightscout, AndroidAPS, Loop
  and xDrip+ appears as four unrelated reports in four channels. Shared intake can connect them,
  tell each project's maintainers, and give the manufacturer one reproducible report. That is the
  benefit a manufacturer gets from the arrangement (§3, last row).
- **Into the quality loop.** A confirmed report becomes a replay vector or regression test in the
  shared kit of the [quality-system proposal](QUALITY-SYSTEM.md#4-the-quality-kit-layer-by-layer).
- **Into data-rights advocacy.** Advocacy for access to device data — renewal comments in the
  Copyright Office's exemption proceedings, submissions to regulators, interoperability and
  right-to-repair work — is stronger with dated, counted cases than with accounts. The intake would
  record, for example, each time a device, app or cloud change cut a person off from their own
  data, how many people and projects it reached, and how long it lasted. The connectors have
  followed vendor-cloud changes since 2020 ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars));
  today none of those cases is recorded in that form.

**Privacy.** Complaint records carry health data and reporters' identities. They are held with
restricted access. Public trackers carry only de-identified summaries, links to the regression test,
and the disposition. Published figures are aggregates with a minimum count, so that no person can be
picked out.

## 7. Credentials for devices that require them

Where a device accepts only an authenticated, authorised client, the shared infrastructure needs:

| requirement | what provides it |
|---|---|
| a recognised client | enrolment of the developer or organisation, and of each release |
| credentials | issuance by an authorised party, protected storage, rotation, revocation |
| permission boundaries | separate authorisation for tiers A, B and C |
| pairing | documented enrolment, replacement, recovery and transfer of a device |
| incident response | the ability to suspend or revoke a compromised client |
| audit | a record of issuance and of security-sensitive actions |
| continuity | disaster recovery, a successor operator, support commitments |
| patient autonomy | access the person can direct, move and withdraw, wherever the device supports it |

**Three roles, kept apart.** A registry of who participates, the authority that issues credentials,
and the hosting of any application are different jobs with different exposure. The credential
authority in particular needs an operator with its own contract, security controls, insurance and
continuity plan ([ECOSYSTEM-PROGRAMME §2b](ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating)).
Issuance has standing only under the manufacturer's authority; a way of distributing credentials
without it does not supply revocation, accountability or a contract.

**No single point of failure for therapy.** A shared identity or credential service must not be able
to stop someone's insulin delivery by being unreachable. Previously authorised, safely bounded local
operation should continue without a connection. The permitted offline behaviour, the expiry rules
and the safe states are defined and validated with each manufacturer. Drawn as three states of one
credential ([idea·credential-lifetime](perspective/STRUCTURES.md#ideacredential-lifetime)):

![Issued and renewed: the credential authority issues and renews the app's grant; the app sends authenticated commands to the pump](perspective/diagrams/idea-credential-lifetime--normal.svg)

![The authority is unreachable: previously authorised, safely bounded operation continues and the person is told the grant's expiry is ahead](perspective/diagrams/idea-credential-lifetime--unreachable.svg)

![Revoked: by process, with published grounds, notice and appeal, at once only for a security incident; commands stop, the pump enters its defined safe state, and the person is told why and how to appeal](perspective/diagrams/idea-credential-lifetime--revoked.svg)

**Separating request from effect.** Identity answers who is asking; authorisation, whether they may;
capability, whether this device and firmware can; and execution evidence, whether it happened. The
last matches the split between `requested` and `applied` state that the
[hub-sync architecture](../30-design/platform/nightscout-hub-sync-architecture-2026-09-11.md) already
makes for state spans.

## 8. Order of work

Five pieces have the best ratio of effort to leverage, and four of them extend work that exists:

1. **A safety intake pilot** (§6): one intake, the three streams, the record shape, an owner, and
   one drill run end to end. New.
2. **Cross-project compatibility tests**: the conformance assertions and replay vectors in
   `conformance/`, extended to one device integration shared by two or more projects.
3. **A release-evidence baseline**: the per-run record of the
   [quality-system proposal](QUALITY-SYSTEM.md#41-the-record-every-run-leaves), plus an SBOM.
4. **Common event schemas**: the schemas in `specs/`, keeping requested and applied state apart.
5. **A readiness dossier**: §3's table, kept current, with a link to the evidence for each row. It
   is what a manufacturer would be handed.

Security contacts and private vulnerability reporting for each project cost little and can start at
once. An operating credential service comes last, after a contract with a manufacturer and funding
for its operator.

## 9. Decisions requested

**For the board:**

1. Whether to seek tier A agreements first and separately (§2).
2. Whether to adopt the rule that the foundation may sponsor shared operations without operating
   them, and does not operate a credential authority itself ([ECOSYSTEM-PROGRAMME §2b](ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating)).
3. Whether to fund a safety intake pilot, and who owns it.
4. Who is the named accountable contact for a manufacturer conversation.

**For the maintainers of the ecosystem projects:**

5. Whether each project would route complaints to a shared intake while keeping its own channels.
6. Whether each project will publish a security contact and turn on private vulnerability reporting.

**For counsel, and for regulatory and quality professionals:**

7. Whether operating a shared intake, or forwarding complaints, creates reporting or record-keeping
   duties for the foundation or for any project.
8. How the terms in §4 and §5 are best written, and in particular how a specification shared in
   confidence can be reconciled with the projects' open-source licences.
9. Whether any selection criteria or exclusivity in an agreement raise competition-law concerns.
10. Which privacy regimes apply to complaint records (HIPAA only through covered-entity relationships;
    otherwise possibly the FTC Health Breach Notification Rule; GDPR for reporters in the EU; for
    reporters in Washington State, the My Health My Data Act, RCW 19.373, whose "regulated entity"
    is "any legal entity" doing business there or targeting its consumers, with no exclusion for
    non-profits, and which gives consent, access and deletion rights over consumer health data).

## 10. Points for reviewers to verify

- **Regulatory references** (§6). The Part 803 time limits and their conditions; the complaint-record
  requirements under the Quality Management System Regulation, effective 2026-02-02, which
  incorporates ISO 13485:2016 (complaint records at 21 CFR 820.35 and ISO 13485 clause 8.2.2). FDA
  reissued its cybersecurity guidance for device submissions in February 2026 to refer to the new
  regulation; confirm its current text before citing what it expects of software suppliers.
- **The measured rows of §3** were read from the governance and evidence pages, measured 2026-10-02.
  Re-measure before the table is given to anyone outside the ecosystem.
- **"No SBOM or build-provenance record"** (§3) is from this repository's surveys, which did not
  search for one specifically. A targeted search should confirm it per project.
- **The tiers** (§2) are a proposal. A manufacturer's own categories may differ, and the agreement
  should use whichever both parties can apply.
- **What happens when a path closes** (§1). The Loop row was read from LoopAlgorithm `7d016fb`, not
  run. AndroidAPS, Trio and iAPS should be read or run for the same case (stale glucose, lost pump
  link) before the table is given to anyone outside the ecosystem.
- **Device supply** (§1). End-of-sale and coverage dates for the devices the open implementations
  support today (Omnipod Eros and DASH, the older Medtronic pumps, Dana, Dexcom G6) have not been
  collected.
