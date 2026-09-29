# Working together across the Nightscout ecosystem — proposal

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, the operators and
companies that host or build on Nightscout, and the community. **DRAFT PROPOSAL for discussion.**
Written 2026-09-29 against this repository at `2c19f61d`. Where it touches conflicts of interest,
partner agreements, trademarks or regulatory status, it needs review by the foundation's counsel
before any decision rests on it (§8). Nothing here is decided.*

*Author's interests: the author maintains cgm-remote-monitor, founded a company that hosts
Nightscout commercially, and could be a candidate for paid work under the sponsored-team proposal.
The rules in §5 would apply to that company and to the author like anyone else.*

## 1. The request

The [ecosystem programme](ECOSYSTEM-PROGRAMME.md) says what the shared layers are. The
[sponsored-team proposal](SPONSORED-TEAM-PROPOSAL.md) says who would do the work nobody is paid
for. This page proposes **the rules for working together** that both depend on, so that
volunteers, app projects, second servers, commercial hosts and researchers can each contribute
without any of them gaining control of what the others rely on.

It asks for five decisions (§7). Each borrows a rule another open-source organisation already
uses (§4), and each answers a need measured in this repository or dated on a vendor's calendar (§3).

## 2. Who takes part, and what each needs

| party | what it needs from the ecosystem | what it can contribute |
|---|---|---|
| people with diabetes and caregivers | alarms and data that keep working; control of their own data | reports of what breaks; consent to research; donations |
| volunteer maintainers of each project | time, review, credit, and the final say over their own project | code, review, release judgment, the history of why things are as they are |
| app projects (Loop, Trio, AndroidAPS, xDrip+, followers) | a server contract that changes only with notice, and tests that say whether it changed | what their apps actually send and expect (the [client census](../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md) covers 40) |
| other servers (Nocturne; any future one) | one current description of the contract and tests any server can run, on equal terms | a second implementation that tests the description; its own parity evidence |
| commercial hosting providers | predictable releases, security fixes on time, and fair treatment beside their competitors | engineering time, test infrastructure, money, operating experience at scale |
| researchers and data holders | consented, well-described data without taking custody of it | studies, methods, aggregate results ([nsprobe](../60-research/collaboration/README.md)) |
| the foundation | a clear reason to exist that donors and members understand; limited liability | the neutral place to hold the shared layers, money and trademarks |

The interests overlap more than they conflict. Every party needs the shared contract to stay
current and the server to be released on time. The conflicts are about **control** (who decides
what the contract is), **credit** (whose work is recognised) and **advantage** (whether any one
company or project is favoured). §5 proposes a rule for each.

## 3. Needs we can predict

Much of the maintenance the ecosystem needs arrives on other organisations' calendars. Dates from
each vendor's own pages, read 2026-09-29; "announced" means the vendor gives a month or year, not a
day.

| date | event | who it reaches |
|---|---|---|
| 2026-10-05 to 11-02 | GitHub's macos-14 runner image has brownouts, then is removed ([runner-images #13518](https://github.com/actions/runner-images/issues/13518)) | Loop, Trio, LoopFollow, LoopCaregiver browser builds still pinned to it |
| 2026-10-28 | Node 26 becomes Active LTS; Node 24 entered maintenance on 10-20 ([Node release schedule](https://github.com/nodejs/Release)) | cgm-remote-monitor, nightscout-connect |
| 2026-11-10 / 11-12 | .NET 8 and 9 end of support ([policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)); PostgreSQL 14 end of life ([versioning](https://www.postgresql.org/support/versioning/)) | Nocturne and its operators |
| early 2027 (announced) | existing Health & Fitness or Medical apps in the EEA, UK and US must declare a regulated-medical-device status in App Store Connect, or "you'll no longer be able to submit app updates" ([Apple, 2026-03-26](https://developer.apple.com/news/?id=nyqbfz1y)) | every person who builds Loop, Trio or a follower app under their own App Store Connect record, if the app meets Apple's criteria |
| 2027 (announced) | Android developer verification expands "to the rest of the world and to all installations"; ADB installs are exempt; every self-built AndroidAPS shares one package name with a different key, which Google says needs additional review ([AndroidAPS docs](https://androidaps.readthedocs.io/en/latest/SettingUpAaps/AndroidDeveloperVerification.html), [Android](https://developer.android.com/developer-verification/guides)) | every AndroidAPS and xDrip+ builder, and sideloaded companion apps |
| April 2027 (announced) | uploads to App Store Connect, TestFlight included, need the iOS 27 SDK / Xcode 27 ([Apple](https://developer.apple.com/news/?id=k1mtkt1k)) | every iOS app builder; builds expire after 90 days, so a missed migration stops the app, not just updates |
| 2027-04-30 | Node 22 end of life, and the Heroku-22 stack end of life the same day: running apps keep running, but deploys are blocked until the stack is upgraded ([Heroku](https://devcenter.heroku.com/articles/heroku-22-stack)) | Nightscout sites on Heroku or on Node 22 |
| August 2027 (announced) | GitHub removes Intel macOS runners ([runner-images #13045](https://github.com/actions/runner-images/issues/13045)) | iOS build workflows pinned to Intel |
| 2027-08-31 | MongoDB 7.0 end of life; Atlas upgrades clusters automatically after notice ([lifecycles](https://www.mongodb.com/legal/support-policy/lifecycles)) | Nightscout sites on Atlas M10+ or self-hosted 7.0 |
| about September 2027 (estimated from cadence) | iOS 28 | iOS apps; each new iOS has historically needed an app release |
| no date | vendor cloud changes: LibreLinkUp alone forced about two connector changes a year from 2023 to 2026 ([sponsored-team proposal §6a](SPONSORED-TEAM-PROPOSAL.md#6a-more-than-one-server)) | every server's connectors |

Three things follow:

- **Most of this reaches several projects at once.** The Apple and Android changes reach every
  self-built app; the runtime and hosting dates reach both servers. Preparing once, in public, is
  cheaper than each project discovering the same change alone.
- **Some of it reaches the people who build the apps, not the projects.** Each builder answers
  Apple's declaration and Google's verification for themselves. What they need is clear, current
  documentation in time; the projects already publish some ([AndroidAPS](https://androidaps.readthedocs.io/en/latest/SettingUpAaps/AndroidDeveloperVerification.html)).
- **None of it can wait for a volunteer's free weekend.** The dates are fixed by others. This is the
  work §4 of the sponsored-team proposal describes.

## 4. What other open-source organisations do

Each rule in §5 comes from one of these. Every figure and quote below was read from the
organisation's own page on 2026-09-29.

| organisation | the rule it uses | source |
|---|---|---|
| Apache Software Foundation | "Apache projects must govern themselves independently of undue commercial influence." No organisation gains control "irrespective of employing Committers … or sponsorship status." The board "does not provide technical direction." | [how it works](https://www.apache.org/foundation/how-it-works/), [the Apache way](https://www.apache.org/theapacheway/), [PMCs](https://www.apache.org/foundation/governance/pmcs.html) |
| Apache | Discussion can happen anywhere, but decisions "should be taken back to the mailing list … If it didn't happen on the mailing list, it didn't happen." | [mailing lists](https://community.apache.org/contributors/mailing-lists) |
| Apache | The Incubator "doesn't fear … internal confrontation between projects which overlap in functionality." | [how it works](https://www.apache.org/foundation/how-it-works/) |
| CNCF | Project websites list support companies "in alphabetical order, or the order can be changed randomly"; "the origin company should not be favored over any other companies offering the same services." | [website guidelines](https://github.com/cncf/foundation/blob/main/policies-guidance/website-guidelines.md) |
| CNCF | Four maturity levels (Sandbox, Incubation, Graduated, Archived). Graduation asks for maintainers from at least two organisations, a code of conduct and a third-party security review. Projects with maintainers from several organisations at entry graduated at 2.07 times the rate of single-organisation projects (59.1% against 28.6%, 72 projects). | [TOC process](https://github.com/cncf/toc/blob/main/process/README.md), [graduation template](https://github.com/cncf/toc/blob/main/.github/ISSUE_TEMPLATE/template-graduation-application.md), [governance guidance, 2026-08-26](https://www.cncf.io/blog/2026/08/26/governance-guidance-for-cncf-projects-choosing-the-right-structure-for-your-projects-size-and-stage/) |
| CNCF | More than $3 million "over the past few years" on security audits and tooling. | [2025 annual report](https://www.cncf.io/wp-content/uploads/2026/03/cncf_ar25_033126a.pdf) |
| Open Home Foundation (Home Assistant) | A nonprofit owns the projects; commercial partners sell products and services and are "contractually required to contribute a majority of its profit from selling licensed products." In 2025 the staff working on foundation projects moved to the foundation. | [structure](https://www.openhomefoundation.org/structure/), [second partner, 2025-12-17](https://newsletter.openhomefoundation.org/meet-our-new-partner-apollo-automation/) |
| OpenStreetMap Foundation | Responsible "for needs that require an organization, and gaps that can not be filled by OSM's volunteer driven community." "Given that volunteer work has not proven to be sufficient in the past, support through paid development is necessary." It offers no commercial services and endorses no company. | [mission](https://osmfoundation.org/wiki/Mission_Statement), [strategic plan](https://osmfoundation.org/wiki/Strategic_Plan), [FAQ](https://osmfoundation.org/wiki/FAQ) |
| OpenMRS (clinical records, 501(c)(3)) | Organisations are recognised at five published levels, from Implementer to Transformative Leader. Staff of implementer organisations "typically contribute 40–50% of all updates in each OpenMRS release." A paid support team handles community operations, product support and QA. | [partners](https://openmrs.org/our-partners/), [get involved](https://openmrs.org/get-involved/), [about](https://openmrs.org/about/) |
| openEHR | Specifications have published states (Planning, Development, Trial, Stable, Paused, Retired). Anyone can raise a problem report; "No change can be made to the specifications without a CR." Conformance profiles are in development. | [change process](https://specifications.openehr.org/governance/change_process), [conformance](https://specifications.openehr.org/releases/CNF/development) |
| OHDSI | A common data model with federated analysis: "data remains at the site behind a firewall. No patient-level data pooling occurs … Only aggregate results are shared." | [Book of OHDSI, ch. 20](https://ohdsi.github.io/TheBookOfOhdsi/NetworkResearch.html) |

### 4a. SQLite: paying for assurance, not control

SQLite is public domain, free to anyone, and built into phones, browsers and aircraft ("Airbus
confirms that SQLite is being used in the flight software for the A350 XWB family"). Its developers
are employed by one small company, Hwaci, and paid from what companies with their own quality and
legal obligations buy. Read from sqlite.org on 2026-09-29:

| what is sold | what the buyer gets | source |
|---|---|---|
| consortium membership, $150K a year on the support page ($120,000 on the member page) | 23 staff-days a year, bug fixes back-ported to any version "no matter how old", regression tests run in the member's own configuration | [consortium](https://sqlite.org/consortium.html), [support](https://sqlite.org/prosupport.html) |
| technical support, $8K to $85K a year | priority support for versions up to a year old | [support](https://sqlite.org/prosupport.html) |
| test runs on the customer's hardware and build options | evidence for the customer's own quality system; the test harness was built to support the avionics standard DO-178B, and every release since 2009 meets 100% MC/DC coverage | [support](https://sqlite.org/prosupport.html), [TH3](https://sqlite.org/th3.html) |
| a "warranty of title", $6,000 once | indemnity for legal departments; "all proceeds … are used to fund continuing improvement and support of SQLite" | [copyright](https://sqlite.org/copyright.html) |

What stays constant across every tier: "technical control and direction of SQLite remains with the
SQLite architect and developers … [it] does not fall under the governance of any single company"
([consortium](https://sqlite.org/consortium.html)). Free users get the same releases, tested the
same way. The developers publish a [quality management plan](https://sqlite.org/qmplan.html)
modelled on DO-178B, and they "plan as if we will be supporting SQLite until 2050"
([long-term support](https://sqlite.org/lts.html)).

What transfers, and what does not:

- **Transfers:** selling assurance rather than influence. Companies that host Nightscout, or build
  on it under their own quality systems, mostly need evidence for a named release, fixes for the
  release line they run, and a support horizon they can cite. The ecosystem already produces much
  of that evidence (the 15.0.9 test matrix, soak runs and client census); what is missing is
  someone paid to package and keep it.
- **Transfers:** a published, sized promise, such as a compatibility promise for the API and a
  support horizon for each release line, kept only as far as funded people can keep it.
- **Does not transfer:** SQLite's "not open-contribution" policy. It works because a salaried team
  writes all the code. The Nightscout projects depend on volunteer and outside contributions.
- **Does not transfer:** the warranty of title. SQLite can offer it because every contributor has
  signed a public-domain affidavit. cgm-remote-monitor is AGPL-3.0 with many contributors and no
  such records; a per-release statement of licences and dependencies is the nearest honest
  equivalent (§8).
- **Check before quoting:** SQLite's own pages disagree on prices (above), and the site makes no
  medical-device quality claim; "medical devices" appears only as an example of where SQLite fits
  ([when to use](https://sqlite.org/whentouse.html)).

## 5. Proposed rules for working together

1. **Decisions go on the public record.** Anyone may propose work, a grant or a change to the shared
   layers. Each proposal gets a public entry, a named reviewer, a response by a published date, and
   a recorded outcome: accepted, declined with reasons, or returned for changes. Conversations can
   happen anywhere; the decision is not made until it is on the record (Apache).
2. **Money and staff buy work, not control.** Contributions of money, people or infrastructure are
   welcome from anyone, on published terms that are the same for everyone. No contribution buys a
   say over what a project merges or what the shared contract says (Apache, OpenStreetMap). Each
   project's maintainers keep the merge decision.
3. **Providers are listed neutrally.** Where the foundation or a project lists hosting providers or
   services, it lists every provider that meets published criteria, in alphabetical or random
   order, and endorses none (CNCF, OpenStreetMap). The Nightscout documentation already lists eight
   hosted providers, each linking to its own site for pricing, with no purchase on the documentation
   domain ([docs home](https://nightscout.github.io/), `docs/index.md` at `9b5afad2`, 2026-08-07).
   The list is not in alphabetical order; under this rule it would be, and T1Pal, the author's
   company, would no longer be listed first.
4. **Contributions are recognised by organisation, every year.** A yearly public report of what
   each organisation contributed (code, review, infrastructure, money, test devices) at published
   levels (OpenMRS). Commercial success then shows up as help to the commons.
5. **One contract, several implementations.** The foundation stewards the API description and the
   conformance tests; servers and apps compete on implementation (openEHR, WHATWG in the
   sponsored-team proposal §6, Apache on overlap). A change to the contract goes through a recorded
   problem-report and change-request process (openEHR).
6. **Two labels, never one.** If projects adopt maturity levels, each project's maintainers propose
   their own level against published criteria (CNCF). A maturity level describes the project's
   organisation and engineering. It says nothing about clinical safety or regulatory status, which
   is a separate statement each project makes for itself.
7. **Data stays with its holder.** Shared research runs as aggregate queries that data holders run
   on their own data (OHDSI; this repository's nsprobe).
8. **Assurance can be paid for; the evidence stays public.** Companies may pay for release
   evidence packaged for their own quality systems, fixes on the release line they run, and test
   runs in their configuration (SQLite). The tests and results that decide a public release stay
   public, fixes land in the public branches, and the money goes to maintenance.
9. **Everyone discloses.** Anyone who decides, reviews or is paid under these rules discloses their
   commercial ties and any interest in the outcome, and steps back from decisions that affect their
   own organisation.

## 6. What would break consensus

- The foundation choosing a winning server or app.
- Influence in proportion to money given.
- Decisions that exist only in private channels.
- A maturity level read as a statement that software is safe for dosing decisions.
- Any account of past disagreements in place of measured needs.

## 7. Decisions requested

**For the board:**

1. Adopt rule 1: where proposals are submitted, the response time, and where outcomes are published.
2. Adopt rules 2, 3 and 9 as policy, with a conflict-of-interest policy that covers board members,
   maintainers, paid staff and partners (counsel, §8).
3. Decide whether to offer a partner programme under rules 2–4 and 8, and what a partner
   contributes and receives.

**For the maintainers of each project:**

4. Whether rules 5–7 are acceptable to your project, and which of §3's dates your project wants
   shared preparation for.

**For the commercial hosting providers:**

5. What each would contribute under equal published terms: engineering time, test infrastructure
   (hosted test sites, CI, devices), or money toward the sponsored team; and which assurance under
   rule 8 (release evidence, fixes on an older line, a support horizon) each would pay for.

## 8. Points for reviewers to verify

For counsel:

1. Whether partner agreements under rules 2–4 raise private-benefit issues for a 501(c)(3), and how
   partner contributions are recorded (donation, sponsorship or contract).
2. Whether listing providers (rule 3) creates any endorsement or liability exposure.
3. Whether selling assurance under rule 8 is related or unrelated business income, and what a
   per-release statement of licences and dependencies may and may not promise, given AGPL-3.0 and
   many contributors (§4a).
4. Whether the foundation should say anything to app builders about Apple's medical-device
   declaration, and if so what; this page gives no regulatory advice, and each builder answers
   Apple for themselves.

For everyone:

5. The §4 quotes were read on 2026-09-29; re-read each before quoting. Not used because they could
   not be verified: an OpenMRS "20+ organisations" figure, and HL7 FHIR connectathon details.
6. The §3 dates marked "announced" or "estimated" will move; re-check before planning against them.
