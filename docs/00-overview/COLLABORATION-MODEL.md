# Working together across the Nightscout ecosystem — proposal

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, the operators and
companies that host or build on Nightscout, and the community. **Recommendation** (part 3 of the
overview; [how the overview is organised](README.md)). **DRAFT PROPOSAL for discussion.**
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

It asks for six decisions (§7). Each borrows a rule another open-source organisation already
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

Much of the maintenance the ecosystem needs arrives on other organisations' calendars: platform,
runtime and hosting dates to the end of 2027, and vendor-cloud changes that arrive with no date.
The dated table, read from each vendor's own pages, is
[evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars).

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

Each rule in §5 borrows from an organisation that already uses it. The rules, quoted from each
organisation's own pages, are in [PRECEDENTS: rules other organisations use](perspective/PRECEDENTS.md#rules-other-organisations-use);
the sizes, funding and commercial roles of the same organisations are in its main table.

### 4a. SQLite: paying for assurance, not control

What SQLite sells, and what stays constant across every tier, is in
[PRECEDENTS: SQLite](perspective/PRECEDENTS.md#sqlite-paying-for-assurance-not-control). For these rules:

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

## 5. Proposed rules for working together

1. **Decisions go on the public record.** Anyone may propose work, a grant or a change to the shared
   layers. Each proposal gets a public entry, a named reviewer, a response by a published date, and
   a recorded outcome: accepted, declined with reasons, or returned for changes. Conversations can
   happen anywhere; the decision is not made until it is on the record (Apache).
2. **Money and staff buy work, not control.** Contributions of money, people or infrastructure are
   welcome from anyone, on published terms that are the same for everyone. No contribution buys a
   say over what a project merges or what the shared contract says (Apache, OpenStreetMap). Each
   project's maintainers keep the merge decision.
3. **Providers are listed neutrally, and payment links say who is paid.** Where the foundation or
   a project lists hosting providers or services, it lists every provider that meets published
   criteria, endorses none (CNCF, OpenStreetMap), and labels any provider run by the project's own
   maintainers or founders as such. The order is set by published criteria and chosen by people
   without a stake in the result: alphabetical, rotating, or by the contribution levels of rule 4.
   Wherever a project's documentation asks for money (a subscription, a donation, a purchase), it
   names who receives it, and money described as going to the foundation goes to a foundation
   account.

   Both servers' documentation already does part of this:

   - Nightscout's lists nine hosted providers, each linking to its own site for pricing, with no
     purchase on the documentation domain ([docs home](https://nightscout.github.io/), `docs/index.md`
     at `9b5afad2`, 2026-08-07). It publishes no listing criteria, and its order follows no stated
     rule; T1Pal, the author's company, is listed first.
   - Nocturne's lists managed instances in a random order on every page load, publishes what a
     provider must supply to be listed, and labels its one entry, nocturne.run, as "the official
     managed Nocturne instance, run by the creator of the project" ([installation
     guide](https://github.com/nightscout/nocturne/blob/main/src/Web/packages/portal/src/routes/docs/installation/%2Bpage.svelte),
     `eba84e58`). Its documentation pages also carry monthly support subscriptions described as going
     to the Nightscout Foundation.
4. **Contributions are recognised by organisation, every year.** A yearly public report of what
   each organisation contributed (code, review, infrastructure, money, test devices) at published
   levels (OpenMRS). Commercial success then shows up as help to the commons.
5. **One contract, several implementations.** The foundation stewards the API description and the
   conformance tests; servers and apps compete on implementation (openEHR, WHATWG in the
   sponsored-team proposal §6, Apache on overlap). A change to the contract goes through a recorded
   problem-report and change-request process (openEHR). Stewarding means hosting the description and
   tests and running that process. The change requests are decided by the maintainers of the
   implementations they affect, with no majority from one employer or host (QUALITY-SYSTEM §8.3),
   so the body that holds the money (rule 2) does not also decide the contract. Any server or
   hosted offering can publish its conformance results from the same public suite (CNCF).
6. **Two labels, never one.** If projects adopt maturity levels, each project's maintainers propose
   their own level against published criteria (CNCF). A maturity level describes the project's
   organisation and engineering. It says nothing about clinical safety or regulatory status, which
   is a separate statement each project makes for itself.
7. **Data stays with its holder.** Shared research runs as aggregate queries that data holders run
   on their own data (OHDSI; this repository's nsprobe).
8. **Assurance can be paid for; the evidence stays public.** Companies may pay for release
   evidence packaged for their own quality systems, fixes on the release line they run, and test
   runs in their configuration (SQLite). The tests and results that decide a public release stay
   public, fixes land in the public branches, and the money goes to maintenance. There is one
   codebase: no separate commercial edition, and no feature held back from people who build and run
   the software themselves.
9. **Everyone discloses.** Anyone who decides, reviews or is paid under these rules discloses their
   commercial ties and any interest in the outcome, and steps back from decisions that affect their
   own organisation.

## 6. What would break consensus

- The foundation choosing a winning server or app.
- A commercial edition that differs from the public one, or evidence that decides a public release
  kept private.
- Influence in proportion to money given.
- Payment decided by one person (Debian's lesson from 2006, [PRECEDENTS](perspective/PRECEDENTS.md#debian-dunc-tank-2006-and-paid-long-term-support-2014)).
- Decisions that exist only in private channels.
- A maturity level read as a statement that software is safe for dosing decisions.
- Any account of past disagreements in place of measured needs.

## 6a. How much structure: the options

The rules in §5 are one point on a range. The board and the maintainers can choose less or more
structure, and the rules can be adopted one at a time. Each option keeps every project's merge
decision with its own maintainers.

| option | what changes | what it costs | what it leaves open | where it is used |
|---|---|---|---|---|
| **0. Remain informal** | nothing: proposals, sponsorship and listings are handled case by case, as today ([GOVERNANCE-TODAY](observations/GOVERNANCE-TODAY.md)) | no new process | outcomes are not on a public record, so readers cannot see how a proposal was handled; no shared rule for companies or for a second server | most small open-source projects |
| **1. A transparency layer** | rule 1 (public proposal record with a named reviewer and a response date) and rule 9 (disclosure); nothing else | a public register and someone to keep it; a response for every proposal | who decides the shared contract, and on what terms companies take part | Apache's "if it isn't on the mailing list, it didn't happen" ([PRECEDENTS](perspective/PRECEDENTS.md#rules-other-organisations-use)) |
| **2. Rules for money and listings** | option 1, plus rules 2–4 and 8: work not control, neutral listings, recognition by organisation, paid assurance with public evidence | written policies and a conflict-of-interest policy (counsel, §8) | how the shared contract changes | OpenStreetMap, CNCF website guidelines, OpenMRS levels, SQLite |
| **3. A cross-project body for the shared contract** | option 2, plus rule 5: the API description and conformance tests change through a recorded change process, decided by maintainers of the affected implementations with no majority from one employer or host | maintainers' time on a standing body; a change-request record | maturity labels (rule 6) and research rules (rule 7) can still be added later | openEHR change requests, WHATWG, CNCF's technical oversight committee, Python's cap on any one employer |

Choosing a lower option now does not rule out a higher one later. CNCF's governance guidance
recommends structure by size, from a maintainer council for a single repository with 3–10
maintainers from 1–3 organisations to an elected steering committee or federated subprojects for
several repositories with 20 or more maintainers from five or more, and says "Governance should not
be more complex than the project" ([CNCF blog, 2026-08-26](https://www.cncf.io/blog/2026/08/26/governance-guidance-for-cncf-projects-choosing-the-right-structure-for-your-projects-size-and-stage/),
read 2026-10-02).

## 7. Decisions requested

**For the board:**

0. Which option in §6a to start from. Decisions 1–4 assume option 1 or above.
1. Adopt rule 1: where proposals are submitted, the response time, and where outcomes are published.
2. Adopt rules 2, 3 and 9 as policy, with a conflict-of-interest policy that covers board members,
   maintainers, paid staff and partners (counsel, §8).
3. Decide whether to offer a partner programme under rules 2–4 and 8, and what a partner
   contributes and receives.
4. Under rule 3, who sets the criteria and the order for provider listings in foundation-stewarded
   documentation, and how payment links that name the foundation are confirmed to reach a
   foundation account.

**For the maintainers of each project:**

5. Whether rules 3 and 5–7 are acceptable to your project, and which of §3's dates your project wants
   shared preparation for.

**For the commercial hosting providers:**

6. What each would contribute under equal published terms: engineering time, test infrastructure
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
