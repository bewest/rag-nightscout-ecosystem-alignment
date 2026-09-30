# Quality management, histories, funders and consensus methods: research notes

*Contributor-facing. Annex to the [stack census record of 2026-09-30](../stack-census-2026-09-30.md); a snapshot, not rewritten as the world moves. Prepared by research agents from the clones and pages named in it, and checked by the session that wrote the record.*

Research notes for the maintainer, prepared 2026-09-30. Every source was read on 2026-09-30 unless a
row says otherwise. Quotes are exact and kept short. This file does not repeat what the
COLLABORATION-MODEL (§4, §4a), the SPONSORED-TEAM-PROPOSAL (§6) or the ECOSYSTEM-PROGRAMME already
cover: Apache, CNCF, the Open Home Foundation's partner rule, OSMF, OpenMRS, openEHR, OHDSI, SQLite's
consortium and pricing, Zig, the Haskell Foundation, WHATWG, W3C, the PSF Developers-in-Residence and
the Sovereign Tech Fellowship.

Disclosure: Alpha-Omega (§C) lists Anthropic among its backers. The model that drafted these notes
is made by Anthropic.

---

## A. SQLite's quality management elements

Sources: [qmplan](https://sqlite.org/qmplan.html) (page stamp "last updated on 2025-11-13"),
[testing](https://sqlite.org/testing.html) (stamp "2026-04-21"; its figures describe "version 3.42.0
(2023-05-16)"), [TH3](https://sqlite.org/th3.html).

| element | what SQLite does | quote | URL |
|---|---|---|---|
| Purpose and size of the plan | A short plan with one test: can a new developer join the team after reading it? | "binders full of incomprehensible jargon that nobody reads. This document strives to break that pattern"; "achieves its purpose if a competent developer can be assimilated into the development team quickly" | [qmplan §1](https://sqlite.org/qmplan.html) |
| What counts as "enough" | Take from DO-178B (the avionics software standard) only the parts that improve quality. Full coverage is kept for the core library because it is so widely deployed, and the team says it would not pay off for a typical application. | "SQLite strives to be nimble and low-ceremony … much of the required DO-178B documentation is omitted. We retain only those parts that genuinely improve quality"; "probably not cost effective for a typical application. However, we think that full-coverage testing is justified for a very widely deployed infrastructure library" | [qmplan §1](https://sqlite.org/qmplan.html), [testing §7.7](https://sqlite.org/testing.html) |
| How the plan was written | They went through DO-178B's list of outputs and kept what applied to them. | "going through the description of outputs in section 11 of DO-178B … and writing down those elements that seemed relevant to SQLite" | [qmplan §1.1](https://sqlite.org/qmplan.html) |
| Life cycle and release cadence | Continuous integration. Releases ship when enough work has built up (historically 5–6 a year). Each release is announced about two weeks ahead, and about a week before it only bug fixes may land ("pencils down"). | "There is no pre-defined release cycle"; "only bug-fix check-ins are allowed on trunk" | [qmplan §2.1–2.1.1](https://sqlite.org/qmplan.html) |
| Release checklist (release gate) | A new checklist for each release. The release ships when every item has turned green. About 200 items are run by hand, and each run records who ran it and when. Past checklists are kept. | "The release occurs when all elements of the checklist are green"; "record when and by whom each validation step was performed"; "not automated … important to keep a human in the loop"; "constantly asking 'Is this really right?'" | [qmplan §2.1.1, §4](https://sqlite.org/qmplan.html), [testing §10](https://sqlite.org/testing.html) |
| The checklist keeps growing | When a new kind of problem turns up, a checklist item is added so it cannot recur. | "As new problems or potential problems are discovered, new checklist items are added" | [testing §10](https://sqlite.org/testing.html) |
| Patch releases | Small hotfixes. Whether a patch gets a checklist is up to the project leader. | "Patch releases may or may not have a release checklist … a judgement call by the project leader" | [qmplan §2.1.2](https://sqlite.org/qmplan.html) |
| Support horizon | They plan to support SQLite through 2050 and comment code for future maintainers. | "used and supported through at least the year 2050"; "maintained by people not yet born" | [qmplan §2.3](https://sqlite.org/qmplan.html) |
| Requirements | The documentation is the requirements. Each requirement is marked up in the docs, and its ID is a hash of its text, so changing the text changes the ID. The docs build generates a matrix of which test cases cover which requirements. | "the 'requirements' are the project documentation"; "impossible to change the requirement text without also changing the requirement number"; "constructs a matrix showing which requirements have been testing" [sic] | [qmplan §6](https://sqlite.org/qmplan.html) |
| Verification objectives | 100% MC/DC (modified condition/decision coverage) in the as-delivered configuration; testing of both source and object code; several platforms and compilers; fuzzing; inspection of every code change; dynamic and static analysis. | "100% MC/DC in an as-delivered configuration"; "Code change inspection" | [qmplan §4](https://sqlite.org/qmplan.html) |
| Four independent test harnesses | TCL tests (public domain, 51,445 cases), TH3 (proprietary, 100% MC/DC, 50,362 cases), SQL Logic Test (checks results against PostgreSQL, MySQL, SQL Server and Oracle), and dbsqlfuzz (private). | "Each test harness is designed, maintained, and managed separately from the others" | [testing §2](https://sqlite.org/testing.html) |
| Test code versus library code | At 3.42.0, 155.8 KSLOC (thousand source lines) of library code against 92,053.1 KSLOC of test code. | "590 times as much test code and test scripts" | [testing §1](https://sqlite.org/testing.html) |
| Fast tests before each check-in | A "veryquick" subset (~304.7k cases) runs before each check-in. Full suites run before a release. | "sufficient to catch most errors, but also run in only a few minutes" | [testing §2](https://sqlite.org/testing.html) |
| Anomaly testing | Simulated out-of-memory, I/O errors, crashes and power loss, and malformed databases. | "instrumented malloc is rigged to fail" | [testing §1.1, §3](https://sqlite.org/testing.html) |
| Defect record becomes a test | A bug is not fixed until a test that reproduces it has been added. | "not considered fixed until new test cases that would exhibit the bug have been added" | [testing §5](https://sqlite.org/testing.html) |
| Coverage and fuzzing pull in different directions | Code tested to 100% MC/DC tends to do worse under fuzzing, because MC/DC discourages defensive code. They run both. | "Fuzz testing and 100% MC/DC testing are in tension" | [testing §4.1.6](https://sqlite.org/testing.html) |
| Evidence track record | Every release since 3.6.17 (2009-08-10) has met 100% branch coverage and MC/DC. TH3 was built for DO-178B and requires a licence. | "TH3 is proprietary and requires a license" | [TH3](https://sqlite.org/th3.html) |
| Configuration management | Fossil (version control plus tickets). Code is mirrored on three servers in three cities with two hosting companies, and developers keep full clones. | "This diversity is intended to avoid a single point of failure" | [qmplan §5.1–5.2](https://sqlite.org/qmplan.html) |
| Verification records | Checklist status and history are kept in their own database, backed up on private servers. The checklist app is in its own repository. | "Release testing proceeds by checklist" | [qmplan §5.4](https://sqlite.org/qmplan.html) |
| Problem reports | Bugs are reported on the public forum and fixed quickly. Fossil tickets hold the history. Forum reports are no longer copied into tickets because the forum is searchable and mirrored. | "All problems are fixed expeditiously"; "it seems unnecessary to duplicate Forum-originated bug reports into the ticket system" | [qmplan §8](https://sqlite.org/qmplan.html) |
| Coding standard | Only three objective rules: 2-space indent, lines of 80 characters at most, no tabs. Everything else is about readability through 2050. | "Objective coding standards for SQLite are minimal" | [qmplan §7](https://sqlite.org/qmplan.html) |
| Static analysis | Code is kept warning-free under -Wall/-Wextra. The team reports that static analysis has found few bugs. | "More bugs have been introduced into SQLite while trying to get it to compile without warnings than have been found by static analysis" | [testing §11](https://sqlite.org/testing.html) |

**What a volunteer ecosystem could adopt from this.** Read against Nightscout's own records (the
15.0.9 test matrix, the soak runs and the probes):

- The pieces that cost the least and pay back most are an **evolving, human-run release checklist
  with a named person and a date per item**, a **bug-to-regression-test rule**, a **"pencils down"
  window before each release**, and **public, mirrored problem reports**. None of them needs paid
  staff.
- The **"requirements are the documentation, hashed and traced to tests"** pattern fits the
  shared-contract layer (the API description and its conformance tests) better than the apps.
- **100% MC/DC does not transfer.** SQLite says it is "probably not cost effective for a typical
  application". The transferable idea is to pick the coverage target per layer by how many people
  depend on that layer, and to state that choice openly. The Zephyr staged approach in §B6 shows one
  way to phase it in.
- SQLite's plan never claims the process is sufficient for any regulator. The page makes no safety
  or certification claim; the DO-178B link is on the TH3 page.

---

## B. Histories

### B1. OpenSSL after Heartbleed (2014–2024)

**What happened.** Heartbleed was disclosed in April 2014 (LWN gives April 3, 2014 as the date the
OpenSSL talk used). On 2014-04-12 Steve Marquess, of the OpenSSL Software Foundation (OSF), wrote
that OSF "typically receives about US$2000 a year in outright donations". One team member worked on OpenSSL without an outside job. Marquess wrote: "There should be at least a half
dozen full time OpenSSL team members, not just one". He also wrote that the roughly US$9,000 of
small post-disclosure donations was "nowhere near enough", and that "The ones who should be
contributing real resources are the commercial companies and governments". OSF also had "about a
hundred grand in open contracts … that aren't being worked because no one … is available".

**What changed.**

- The Linux Foundation's Core Infrastructure Initiative (CII) paid for "fellowships for key
  developers to work fulltime", security audits and test infrastructure. "OpenSSL will receive funds
  from CII for two, fulltime core developers", and the Open Crypto Audit Project was funded to audit
  the code.
- By LWN's 2016 account: "Before April 2014, OpenSSL had two primary developers, both of whom were
  volunteers, and no decision-making process. As of December of that year, the project had 15
  members, two of whom are paid full-time by CII and two others who are paid from donations". The
  project wrote "major policies, covering release strategies, security, coding style". Its support
  policies became "well defined", including its first LTS (long-term support) release. "All code must
  be formally reviewed before being committed". It set a goal to respond to all reports within four
  days.
- 2024-07-24: the OpenSSL Management Committee was dissolved and replaced by "two independent but
  co-equal entities": the OpenSSL Foundation ("non-commercial communities") and the OpenSSL
  Corporation ("commercial communities"). Each has a ten-member board and community-elected
  business and technical advisory committees.

**Lesson for Nightscout.** Money arrived after a visible failure. What turned it into a functioning
project was people funded *per role* (two CII fellows) plus written policies: a release strategy,
support horizons per release line, mandatory review and a target response time. Money on its own
did not do that. The 2024 split is a precedent for keeping a commercial side and a community side
apart while both serve one mission.

**Sources.**
[Marquess, 2014-04-12](https://web.archive.org/web/2014/http://veridicalsystems.com/blog/of-money-responsibility-and-pride/),
[LF CII first projects](https://www.linuxfoundation.org/press/press-release/the-linux-foundations-core-infrastructure-initiative-announces-new-backers-first-projects-to-receive-support-and-advisory-board-members),
[LWN "OpenSSL after Heartbleed", 2016-10-06](https://lwn.net/Articles/702751/),
[OpenSSL governance announcement, 2024-07-24](https://mta.openssl.org/pipermail/openssl-users/2024-July/017298.html),
[OpenSSL Foundation](https://openssl-foundation.org/).

### B2. xz-utils backdoor (2024)

**What happened.**

- 2022-06-08: the maintainer, Lasse Collin, replied publicly on xz-devel to a poster pressing for a
  new maintainer: "my ability to care has been fairly limited mostly due to longterm mental health
  issues"; "this is an unpaid hobby project"; he had "worked off-list a bit with Jia Tan … perhaps
  he will have a bigger role in the future".
- 2024-03-29: Andres Freund disclosed that "The upstream xz repository and the xz tarballs have been
  backdoored". Part of the backdoor was "solely in the distributed tarballs", which were created and
  signed by the co-maintainer. The same day CISA advised users to "downgrade XZ Utils to an
  uncompromised version—such as XZ Utils 5.4.6 Stable".
- The maintainer's own incident page records that clean releases were made on 2024-05-29.

**What changed.**

- 2024-04-12, CISA (Cable and Black) named "the very real and ongoing risks created by maintainer
  burnout" and said "the burden of security shouldn't fall on an individual open source
  maintainer". Companies "must contribute back – either financially or through developer time".
- 2024-04-15, OpenSSF and the OpenJS Foundation reported a similar attempted takeover and listed
  warning patterns: "Friendly yet aggressive and persistent pursuit of maintainer"; "Request to be
  elevated to maintainer status by new or unknown persons"; "A false sense of urgency". Their
  statement: "Ensuring our maintainers are well supported is the primary deterrent". They also
  recommended "a second developer conduct code reviews before merging, even when the PR comes from a
  maintainer".

**Lesson for Nightscout.** A lone unpaid maintainer is a security risk as well as a staffing risk,
and the attack targets exactly the moment help is welcome. Two practices are cheap here:

- **Release artefacts reproducible from the repository.** The backdoor was only in the tarballs.
  For Nightscout this means Docker images and app builds.
- **An earned-trust path to maintainer rights**, with review by a second person.

**Sources.**
[Collin, xz-devel 2022-06-08](https://www.mail-archive.com/xz-devel@tukaani.org/msg00567.html),
[Freund, oss-security 2024-03-29](https://www.openwall.com/lists/oss-security/2024/03/29/4),
[tukaani.org incident page](https://tukaani.org/xz-backdoor/),
[CISA alert 2024-03-29](https://www.cisa.gov/news-events/alerts/2024/03/29/reported-supply-chain-compromise-affecting-xz-utils-data-compression-library-cve-2024-3094),
[CISA "Lessons from XZ Utils", 2024-04-12](https://www.cisa.gov/news-events/news/lessons-xz-utils-achieving-more-sustainable-open-source-ecosystem),
[OpenSSF/OpenJS alert 2024-04-15](https://openssf.org/blog/2024/04/15/open-source-security-openssf-and-openjs-foundations-issue-alert-for-social-engineering-takeovers-of-open-source-projects/).

### B3. Log4Shell (2021) and curl

**Log4Shell.** On 2021-12-16 Brian Behlendorf (OpenSSF) wrote that ASF's "volunteer security team
worked with the Log4j maintainers and responded quickly", despite being notified "just before the
Thanksgiving holiday". Log4j had "almost 8000 passing tests in its CI pipeline, but even all that
testing didn't catch" the flaw. His recommendations were:

- Foundations should fund "regular paid audits for their most critical projects, scanning tools and
  CI", and keep "at least a few paid staff members on a cross-project security team so that
  time-critical responses aren't left to individual volunteers".
- A caution that "it would be an insult to most maintainers to suggest that if you'd just slipped
  more money into their pockets they would have written more secure code". [OpenSSF blog](https://openssf.org/blog/2021/12/16/open-source-foundations-must-work-together-to-prevent-the-next-log4shell-scramble/)

**curl.**

- Daniel Stenberg spent "two hours or so of my spare time on that project – every day for over
  twenty years". In 2014 he joined Mozilla, which let him spend some work hours on curl.
- He then joined wolfSSL: "We sell curl support and related services to companies. Companies pay
  wolfSSL, wolfSSL pays me a salary". He has been "working full-time on curl since 2019".
  [Working open source, 2020-10-26](https://daniel.haxx.se/blog/2020/10/26/working-open-source/),
  [The pressure, 2026-05-26](https://daniel.haxx.se/blog/2026/05/26/the-pressure/)
- The project's [sponsors page](https://curl.se/sponsors.html) says "wolfSSL employs Daniel and lets
  him spend paid work hours on curl". Donations go to Open Source Collective, a 501(c)(6)
  ([donate](https://curl.se/donation.html)).
- 2022-10-19: the Sovereign Tech Fund paid two developers for six months on three projects. Stenberg
  wrote: "we got to decide and plan what we wanted done" and "Everything will be done in the open".
  [Funded curl improvements](https://daniel.haxx.se/blog/2022/10/19/funded-curl-improvements/)
- In 2024 the curl fund, "entirely and only of money donated to the project", paid a second
  developer's work. [Funding Stefan's curl work, 2024-01-09](https://daniel.haxx.se/blog/2024/01/09/funding-stefans-curl-work/)
- On 2025-07-23 he wrote that maintenance cannot be expected "to be done by volunteers on their
  spare time". [EU-STF post](https://daniel.haxx.se/blog/2025/07/23/eu-stf-for-funding-critical-open-source/)
- The bug bounty ended 2026-01-31, after "87 confirmed vulnerabilities and over 100,000 USD paid",
  because of low-quality AI-generated reports: "We suspect the idea of getting money for it is a big
  part of the explanation". [End of the bug bounty, 2026-01-26](https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/)

**Lesson for Nightscout.** curl's structure is close to Nightscout's: one company employs the lead
by selling support, and the project stays independent and in the open. What curl added was a
**project-held fund with public deliverables**, and **time-boxed public grants whose scope the
project wrote**. The bug-bounty ending is a warning that paying per report can attract noise.

### B4. Debian: volunteer project, paid LTS, and Dunc-Tank (2006)

**Dunc-Tank (2006).** LWN reported the plan (2006-09-27) "to pay Debian release managers [two named
release managers] to work full time on the Debian Etch release, for a period of one month
each". The board of this independent group included the sitting Debian Project Leader (DPL) and his
assistant. LWN asked: "If the DPL is involved, doesn't that make it a Debian Project?"
[LWN 201488](https://lwn.net/Articles/201488/)

- A general resolution to recall the DPL failed ("0.173 (48/277)"). [vote_005](https://www.debian.org/vote/2006/vote_005)
- The winning option read: "The Debian Project does not object to the experiment … However, this
  particular experiment is not the result of a decision of the Debian Project". [vote_006](https://www.debian.org/vote/2006/vote_006)
- A 2006-10-26 position statement from about 20 signers objected that the choice of the release
  managers was unexplained, asked what exactly the pay was for, and warned of a two-class system of
  paid members above unpaid ones. It said the experiment had already demotivated contributors
  (summary obtained through a fetch tool, so quote from the original before use:
  [debian-devel-announce](https://lists.debian.org/debian-devel-announce/2006/10/msg00026.html)).
- Etch shipped on 2007-04-08, after the planned December 2006 date. [Debian news](https://www.debian.org/News/2007/20070408)
- In 2019 Raphaël Hertzog drew the lesson "don't let the DPL decide alone who gets paid", and noted
  that "the jealousy aspect was likely more problematic than it would be today". Holger Levsen
  replied that LTS differs because the money "is handled completely outside of the Debian project".
  [LWN 790954, 2019-06-12](https://lwn.net/Articles/790954/)

**Freexian and Debian LTS.**

- Debian LTS "is not handled by the Debian Security and Release teams", but "by a group of
  volunteers and companies". "The number of properly supported packages depends directly on the
  level of support that the LTS team receives." [Debian wiki LTS](https://wiki.debian.org/LTS)
- Freexian: "Debian used to provide only 3 years of security support"; now 5 years, "thanks to … the
  Debian LTS team: composed mainly of paid developers, most of them are funded by Freexian". It has
  paid contributors "since 2014" and publishes monthly reports. Sponsor benefits include the right to
  "Influence the work of sponsored developers". [Freexian LTS](https://www.freexian.com/lts/debian/)

**Lesson for Nightscout.** A volunteer-only project accepted paid work because the paid work was:

1. **a separate, named service** (LTS after the security team's term ends);
2. **funded and run outside the project's own treasury and governance**;
3. **reported monthly in public**.

The failure mode Debian recorded was paying a hand-picked few project officers for ordinary project
work, chosen by one leader, with no stated deliverable.

### B5. Home Assistant / Open Home Foundation (new facts only)

The partner rule is already in COLLABORATION-MODEL §4. New facts:

- The partner contributions let the foundation "support more than 50 full-time employees".
- Nabu Casa, founded in 2018, "stewarded the cause of Home Assistant without commercializing the
  open source project itself", and for years "a significant portion of Nabu Casa's revenue was used
  to pay the salaries". [structure](https://www.openhomefoundation.org/structure/)

**Lesson for Nightscout.** It is the closest structural match: one founder-linked commercial host
paid maintainers for years. Formalising that into a foundation with a published profit-share rule
came six years later (2024), and moving the employees came in 2025.

### B6. Safety evidence in open source: ELISA and Zephyr

- **ELISA** launched 2019-02-21 "to create a shared set of tools and processes to help companies
  build and certify Linux-based safety-critical applications". It names "medical devices" among its
  targets, and says "there is no clear method for certifying Linux". ELISA works "with certification
  authorities and standardization bodies". Founding members: Arm, BMW Car IT, KUKA, Linutronix,
  Toyota. [launch release](https://elisa.tech/announcement/2019/02/21/the-linux-foundation-launches-elisa-project-enabling-linux-in-safety-critical-systems/),
  [elisa.tech](https://elisa.tech/)
- **Zephyr** (an open-source real-time operating system):
  - Its safety committee's scope is "to achieve a certification for the IEC 61508 standard" (the
    general functional-safety standard) at "SIL 3 / SC 3" (safety integrity level 3 / systematic
    capability 3) "for a limited source scope (see certification scope TBD)". Because the code
    already existed, it uses the standard's "route 3s/1s" (assessment of existing code).
  - "Functional safety considers quality as an existing pre-condition and therefore the 'quality
    managed' status should be pursued for any project regardless of the functional safety goals."
  - Coding rules are adopted in stages. Stage I: rules "available … but not enforced" (completed).
    Stage II: reviewers may block PRs, "initially … the safety certification scope". Stage IV:
    extend to the whole codebase, with exceptions needing TSC (technical steering committee)
    approval. [Zephyr safety overview](https://docs.zephyrproject.org/latest/safety/safety_overview.html)

**Lesson for Nightscout.**

- Safety evidence is being built in the open by *companies that need it*, not by volunteers.
- Two patterns fit here:
  - **Limit the scope first.** The certification scope is a subset of the code.
  - **Enforce in stages.** Publish the rules, then enforce them on a small scope, then widen.
- Keep the two-labels rule (COLLABORATION-MODEL §5 rule 6). ELISA's aim is that a *company* can
  certify *its* system. The project itself does not claim certification.

### B7. KernelCI: a shared testing commons

KernelCI "was originally started in 2014 as a side project by a few engineers who were doing the
testing at home and in their spare time". It became a Linux Foundation project on 2019-10-28,
"underwritten by BayLibre, Civil Infrastructure Platform, Collabora, Foundries.io, Google,
Microsoft, Red Hat". The case for it: "Linux kernel testing is often fragmented since it is largely
done in private silos". [2019 release](https://kernelci.org/news/2019/10/28/distributed-linux-testing-platform-kernelci-secures-funding-and-long-term-sustainability-as-new-linux-foundation-project/),
[kernelci.org](https://kernelci.org/)

**Lesson for Nightscout.** A volunteer test lab became shared infrastructure once the companies that
relied on it paid for it as a member fund. The same could hold here: device and replay labs that
hosts and app builders each run privately, pooled as one shared lab (sponsored-team proposal §6a
already proposes a shared connector lab).

### B8. The ecosystem's own history: #WeAreNotWaiting, OpenAPS, Tidepool Loop

- The first D-Data ExChange (Fall 2013, Stanford) "was the birthplace of the #WeAreNotWaiting
  hashtag". [D-Data about](https://ddataexchange.com/about/)
- DIYPS was created in December 2013. "#OpenAPS was created in February 2015".
  [diyps.org bio](https://diyps.org/dana-lewis/)
- OpenAPS describes itself as "a safety-focused reference design, an open source reference
  implementation, and documentation that can be used by any individual – or any medical device
  manufacturer". Its design falls back to scheduled basal "whenever it receives conflicting
  information … (or when required information is missing)".
  [what is OpenAPS](https://openaps.org/what-is-openaps/), [reference design](https://openaps.org/reference-design/)
- FDA 510(k) K203689, "Tidepool Loop", was classified as an "Interoperable Automated Glycemic
  Controller" (product code QJI). It was received 12/17/2020 and decided 01/23/2023 as "Substantially
  Equivalent". [FDA database](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K203689)
- Tidepool, 2023-01-24: "the first ever community led innovation in the diabetes space to be FDA
  cleared … as a 501(c)(3) nonprofit". It credits the open-source DIY Loop work, RileyLink, and the
  Jaeb Center's observational study of DIY Loop users. The clearance "can now become a predicate
  device" (a device later 510(k) submissions can compare themselves against).
  [Tidepool blog](https://www.tidepool.org/blog/tidepool-loop-has-received-fda-clearance)
- 2024-03-18: Sequel's twiist AID system "incorporates FDA-cleared Tidepool Loop technology".
  [press release](https://www.globenewswire.com/news-release/2024/03/18/2847675/0/en/Sequel-s-twiist-Automated-Insulin-Delivery-System-Receives-FDA-510-k-Clearance.html)

**Lesson for Nightscout.** The ecosystem already has a precedent. A nonprofit took volunteer-written
open-source dosing software through regulatory clearance. That took its own paid team, and real-world
evidence from the community (the observational study). The DIY project continued alongside.
Regulated and DIY tracks can coexist; each needs its own label (COLLABORATION-MODEL §5 rule 6).

### B9. Studies on volunteer and paid maintainers

- **Roads and Bridges** (Nadia Eghbal, Ford Foundation, 2016):
  - "Money alone will not fix a struggling infrastructure project, because open source thrives on
    human rather than financial resources."
  - "embracing the concept of stewardship rather than control."
  - "Long-term support is more about creating time than it is about money."
  - Maintainers benefit from being able "to plan for the next three to five years, not just six
    months to a year."
  - [PDF](https://www.fordfoundation.org/wp-content/uploads/2016/07/roads-and-bridges-the-unseen-labor-behind-our-digital-infrastructure.pdf)
- **Tidelift 2024 maintainer report** (n=437). Tidelift sells paid maintenance, so it has an interest
  in the result.
  - 60% describe themselves as unpaid. 16% are "unpaid hobbyist[s] and do not want to get paid", and
    44% would appreciate pay.
  - "Sixty-one percent of unpaid maintainers are solo maintainers", against 26% of paid maintainers.
  - Paid maintainers are "8-26 percentage points (or, on average 55%) more likely to implement" the
    security and maintenance practices surveyed.
  - 60% "have either quit or considered quitting" (22% quit, 38% considered it; n=350).
  - The report cautions on causality: "It's hard to definitively say what is a cause and what is an
    effect here."
  - [PDF](https://assets-eu-01.kc-usercontent.com/ef593040-b591-0198-9506-ed88b30bc023/d325a56f-05be-4379-bfd1-ee4776fcad41/2024-tidelift-state-of-the-open-source-maintainer-report-.pdf)
- **Census II** (Linux Foundation and Harvard LISH, March 2022), as summarised by the LF:
  - "136 developers were responsible for more than 80% of the lines of code added to the top 50
    packages."
  - Many of the most-used packages "were hosted on individual (personal) developer accounts".
  - [linux.com summary](https://www.linux.com/news/a-summary-of-census-ii-open-source-software-application-libraries-the-world-depends-on/)

---

## C. Funders for maintenance and security

| funder | what it pays for | eligibility | health/medical precedent? | URL |
|---|---|---|---|---|
| Alpha-Omega (OpenSSF-associated; backed by Anthropic, AWS, Citi, GitHub, Google, Google DeepMind, Microsoft, OpenAI; "annual budget of over $7M") | Security improvements, directly or through audits: "funding to maintainers intended to improve the project's overall security quality" | Standalone projects, foundations and "core ecosystem services" under an OSI-approved licence. Applicants must show criticality and current security posture. Rounds run quarterly, with a co-designed statement of work in month 2. Agreements "will not be heavy with timelines", but "future funding depends on meaningful progress" | None found on the pages read | [home](https://alpha-omega.dev/), [how to apply](https://alpha-omega.dev/grants/how-to-apply/) |
| Sovereign Tech Fund (Sovereign Tech Agency, German federal) | Development and maintenance of "open digital base technologies"; audits allowed where needed. Projects abroad are eligible (curl was funded) | Work over €50,000; FOSS licence; no other public funding for the same work; "We do not finance the development of prototypes"; "currently not looking for user-facing applications". Criteria include "critical sectors of society (e.g., education, health care …)" | Health care is named as a public-interest criterion; no funded health project found in the list read | [fund](https://www.sovereign.tech/programs/fund), [tech list](https://www.sovereign.tech/tech) |
| NLnet / NGI Zero (EU-funded, NLnet Foundation independent since 1989) | Small R&D and maintenance grants, paid against milestones, across "the whole technology spectrum … to convenient end user applications" | First grant up to €50k; later ones up to €150k each and €500k per recipient, only after earlier projects conclude with public, openly licensed deliverables. Projects need a "clear European Dimension". Larger grants may be audited, with payment "conditional to the outcome". Review committee members are unpaid and have no economic ties | **Yes**: Goupile ("data collection in research, particularly in health", eCRF, InterHop; NGI Zero Core 2024), and a GNU Taler / GNU Health integration (NGI Taler 2024). The Commons Fund's "thirteenth and final call … closed on June 1st 2026"; other NLnet programmes remain (next deadline 2026-11-03) | [Commons Fund](https://nlnet.nl/commonsfund/), [guide](https://nlnet.nl/commonsfund/guideforapplicants/), [Goupile](https://nlnet.nl/project/Goupile/), [projects](https://nlnet.nl/project/) |
| Linux Foundation CII (2014), historical | Fellowships for full-time developers, audits, test infrastructure | Critical, underfunded infrastructure, chosen by a steering committee and advisory board | None | [LF release](https://www.linuxfoundation.org/press/press-release/the-linux-foundations-core-infrastructure-initiative-announces-new-backers-first-projects-to-receive-support-and-advisory-board-members) |
| Rust Foundation Maintainers Fund (announced 2025-11-04) | "consistent, transparent, and long term support" for Rust maintainers, including "pull request reviews … upgrades, refactorings" | Rust Project maintainers only. Structure to be set "in close collaboration with the Rust Project Leadership Council … openly and with accountability" | Not applicable | [announcement](https://rustfoundation.org/media/announcing-the-rust-foundation-maintainers-fund/) |
| FreeBSD Foundation (501(c)(3)) | "contract development of critical system infrastructure"; "over 60%" of funding goes to software development | Its own project only | Not applicable | [about](https://freebsdfoundation.org/about-us/about-the-foundation/), [FAQ](https://freebsdfoundation.org/about-us/faq/) |

Fit for Nightscout:

- **NLnet is the only funder read that has funded health software**, and its small grants with
  public milestones match volunteer-sized work. The European-dimension requirement needs checking
  for a US 501(c)(3).
- The **STF excludes user-facing apps**. The shared layers (the API contract, the conformance suite,
  the connector libraries, the BLE protocol libraries) are the plausible "base technology".
- **Alpha-Omega** fits a security audit of cgm-remote-monitor's auth plane and the connectors.

---

## D. Consensus methods

| method | organisation | how it works | what it would look like here | URL |
|---|---|---|---|---|
| RFC with final comment period | Rust | "Substantial" changes need an RFC. A sub-team member moves a "final comment period" (FCP) with a disposition (merge, close or postpone). This "does not require consensus amongst all participants … (which is usually impossible)", but there "should not be a strong consensus *against*". All sub-team members sign off. The FCP lasts "ten calendar days" and is advertised widely. Long threads get a "summary comment" first | Shared-contract changes (API fields, auth, entries schema) as PRs in one proposals repository. The owning maintainers move the FCP; a 10-day window is announced in every app community's channel | [rust-lang/rfcs](https://github.com/rust-lang/rfcs) |
| Project goals | Rust (RFC 3614, 2024) | "Goals are a contract between the owner and project teams. The owner commits to doing the work. The project commits to supporting that work." "Goals cover a problem, not a solution." "Nothing good happens without an owner." They are reset every six months. Declared goals make it "easier for people to make commitments to would-be employers" | A six-monthly slate of ecosystem goals, each with a named owner (paid or volunteer) and the teams that support it. It gives funders something defined to pay for, without buying the solution | [RFC 3614](https://github.com/rust-lang/rfcs/blob/master/text/3614-project-goals.md), [goals.rust-lang.org](https://goals.rust-lang.org/) |
| PEP with champion | Python (PEP 1) | Each PEP has a champion who "is responsible for building consensus within the community and documenting dissenting opinions". The Steering Council accepts or rejects it | Every requirement proposal records its dissent section. This is the natural home for the volunteer-only view | [PEP 1](https://peps.python.org/pep-0001/) |
| Elected council with an employer cap | Python (PEP 13) | A "5-person committee" elected by the core team after each feature release. "Instead of voting, it's better to seek consensus". "Members with conflicts of interest … must abstain". "at most 2 members of the council can work for any single employer" | A cross-project council with an explicit cap per employer or host company, so that no single host is a majority | [PEP 13](https://peps.python.org/pep-0013/) |
| Enhancement proposal with states and approvers | Kubernetes (KEP) | States: `provisional`, `implementable`, `implemented`, `deferred`, `rejected`, `withdrawn`, `replaced`. "A single SIG will own the KEP"; approvers span the affected SIGs and "should be a distinct set from authors" (a SIG is a special interest group) | Requirement records with published states, and approvers from the client projects affected (Loop, Trio, AAPS, xDrip+) who did not write the proposal | [KEP-0000](https://github.com/kubernetes/enhancements/blob/master/keps/sig-architecture/0000-kep-process/README.md) |
| Rough consensus | IETF (RFC 7282, 2014) | "not … 'majority rule'". "Lack of disagreement is more important than agreement." "Rough consensus is achieved when all issues are addressed, but not necessarily accommodated." Humming "should be the start of a conversation, not the end" | The chair's test for each requirement: has every objection had a recorded answer? Objections are not counted, and a "no" is answered in writing rather than outvoted | [RFC 7282](https://www.rfc-editor.org/rfc/rfc7282) |
| Requirements = documentation, hashed and traced | SQLite | Requirement text is marked up in the docs, its ID is its hash, and the build outputs a coverage matrix from requirements to tests | The API description's normative statements get stable IDs, and the conformance suite reports which IDs it covers | [qmplan §6](https://sqlite.org/qmplan.html) |

---

## E. The volunteer-only position: steelman and reconciliations

### Steelman

The case for zero paid maintainers, in its strongest form:

1. **Independence and no capture.** Whoever pays sets priorities, even without intending to.
   Freexian's LTS offer lists the right to "Influence the work of sponsored developers" among its
   sponsor benefits ([Freexian](https://www.freexian.com/lts/debian/)). In a dosing-adjacent
   ecosystem, a priority set by a host's commercial needs could shift safety work.
2. **Community ownership and fairness.** Paying some people creates the "two-class" split Debian's
   2006 signers described, and a demotivated volunteer base
   ([position statement](https://lists.debian.org/debian-devel-announce/2006/10/msg00026.html)).
   Debian's 2019 look back named the "jealousy aspect"
   ([LWN 790954](https://lwn.net/Articles/790954/)).
3. **Motivation is not bought.** "open source thrives on human rather than financial resources"
   ([Roads and Bridges](https://www.fordfoundation.org/wp-content/uploads/2016/07/roads-and-bridges-the-unseen-labor-behind-our-digital-infrastructure.pdf)).
   "an insult to most maintainers to suggest that if you'd just slipped more money into their pockets
   they would have written more secure code" ([Behlendorf](https://openssf.org/blog/2021/12/16/open-source-foundations-must-work-together-to-prevent-the-next-log4shell-scramble/)).
   Some maintainers do not want pay: 16% in Tidelift's 2024 survey.
4. **Money is fragile.** A paid seat ends when the sponsor leaves (sponsored-team proposal §6,
   Haskell Foundation). A project built around salaries can shrink when funding stops. A volunteer
   project has no payroll to lose.
5. **Money brings its own noise.** curl ended its bug bounty because "the idea of getting money for
   it is a big part of the explanation" of the flood of reports
   ([Stenberg](https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/)).
6. **The regulatory boundary.** DIY tools are built and run by users themselves. Paid development
   could blur that line. Tidepool shows the regulated path is a separate, heavier undertaking
   (§B8).

### Reconciliations found in other projects

| reconciliation | where it worked | the safeguard that made it acceptable | source |
|---|---|---|---|
| Pay for a separate, named service, outside the project | Debian LTS via Freexian (since 2014) | Money "handled completely outside of the Debian project"; LTS "is not handled by the Debian Security and Release teams"; monthly public reports | [LWN 790954](https://lwn.net/Articles/790954/), [Debian wiki](https://wiki.debian.org/LTS), [Freexian](https://www.freexian.com/lts/debian/) |
| Pay for roles, chosen by a group, not one leader | Lesson drawn from Dunc-Tank | "don't let the DPL decide alone who gets paid"; the project stated that the experiment "is not the result of a decision of the Debian Project" | [LWN 790954](https://lwn.net/Articles/790954/), [vote_006](https://www.debian.org/vote/2006/vote_006) |
| Pay for infrastructure and assurance, not code direction | CII (fellows, audits, test infrastructure); KernelCI (member-funded testing); Behlendorf's paid audits, CI and a cross-project security team | Money goes to shared services that volunteers find hard to sustain; maintainers keep merge authority | [CII](https://www.linuxfoundation.org/press/press-release/the-linux-foundations-core-infrastructure-initiative-announces-new-backers-first-projects-to-receive-support-and-advisory-board-members), [KernelCI](https://kernelci.org/news/2019/10/28/distributed-linux-testing-platform-kernelci-secures-funding-and-long-term-sustainability-as-new-linux-foundation-project/), [OpenSSF](https://openssf.org/blog/2021/12/16/open-source-foundations-must-work-together-to-prevent-the-next-log4shell-scramble/) |
| Time-boxed grants with public deliverables, scoped by the project | curl and the STF (six months, three projects "we got to decide and plan"); NLnet (milestone payments, public open-licensed deliverables before any larger grant) | The deliverables are public and fixed in advance; the project writes the scope; the grant ends | [curl](https://daniel.haxx.se/blog/2022/10/19/funded-curl-improvements/), [NLnet guide](https://nlnet.nl/commonsfund/guideforapplicants/) |
| Volunteer-first, with a paid backstop | Behlendorf: paid security staff "so that time-critical responses aren't left to individual volunteers" | Paid people cover response time and the unglamorous work; features stay open to everyone (matches sponsored-team §5) | [OpenSSF](https://openssf.org/blog/2021/12/16/open-source-foundations-must-work-together-to-prevent-the-next-log4shell-scramble/) |
| Pay for a declared goal, not a person | Rust project goals; the Rust Maintainers Fund set with the Leadership Council | "Goals cover a problem, not a solution"; "owners make proposals, but teams are ultimately the ones that decide"; funding decisions "made openly and with accountability" | [RFC 3614](https://github.com/rust-lang/rfcs/blob/master/text/3614-project-goals.md), [Rust Foundation](https://rustfoundation.org/media/announcing-the-rust-foundation-maintainers-fund/) |
| Cap any one employer's weight in governance | Python Steering Council | "at most 2 members of the council can work for any single employer"; members abstain on conflicts | [PEP 13](https://peps.python.org/pep-0013/) |
| Keep commercial and community sides structurally separate | OpenSSL Foundation / Corporation (2024); Open Home Foundation with profit-share partners | "two independent but co-equal entities"; partners "contractually required to contribute a majority of its profit" | [OpenSSL](https://mta.openssl.org/pipermail/openssl-users/2024-July/017298.html), [OHF](https://www.openhomefoundation.org/structure/) |
| Project-held fund from donations, spent on named work | curl fund | "consists entirely and only of money donated to the project"; each funded project is announced | [curl](https://daniel.haxx.se/blog/2024/01/09/funding-stefans-curl-work/) |

**A requirement set that could meet both views.** Each item below comes from the rows above:

1. No payment decided by one person.
2. Paid work is a named role, service or goal with public deliverables and an end date.
3. The money is held and disbursed outside project merge authority.
4. Paid people cannot approve their own work.
5. There is an employer or host cap on any deciding body.
6. A monthly public report.
7. Volunteer maintainers keep merge authority.
8. Dissent is recorded in each proposal (PEP 1) and answered, not outvoted (RFC 7282).

The volunteer-only position then has a standing test: if paid work ever changed a merge decision or
went unreported, rule 7 or rule 6 has been broken, and that can be checked in public.

---

## F. Things I could not verify

- **OpenSSL staffing after 2016** and the current foundation and corporation headcount or budgets.
  Only LWN's December 2014 figure (15 members, 2 paid by CII, 2 paid from donations) was read.
- **CII's transition into OpenSSF** (commonly dated 2020): not read from a primary source.
- **Dunc-Tank's measured effect.** The claim that it delayed Etch or demotivated contributors comes
  from the signers' position statement, read only through a fetch-tool summary; the page could not be
  fetched directly. The late release date (2007-04-08) is verified. Cause and effect are not.
- **Log4j maintainers' paid or volunteer status** from the ASF's own posts: the ASF blog did not
  return text. Only Behlendorf's description of ASF's "volunteer security team" was read.
- **Census II figures** were read from the Linux Foundation's summary, not the report PDF.
- **Zephyr and ELISA outcomes**: whether any IEC 61508 certificate has been issued. Zephyr's own
  page says "certification scope TBD".
- **Tidepool Loop as a standalone app** available to users: not verified. Only the 510(k) record and
  its use inside twiist (2024-03-18) are verified.
- **Health or medical grants** by Alpha-Omega or the STF: none found. That is not proof there are
  none.
- **NLnet's European-dimension rule** and whether a US 501(c)(3) could qualify: not checked.
- **Rust Foundation Maintainers Fund**: its structure and first payouts after 2025-11-04 were not
  read.
- **The one full-time member's pre-Heartbleed status** is Marquess's 2014 account, not that member's own.
- **SQLite's requirements page** (`requirements.html`) returned only navigation, so the
  requirement-hash mechanism is quoted from qmplan §6 alone.
- **Linux.com's Census summary and Tidelift's report** are published by parties with an interest
  (the LF, and a vendor of paid maintenance). The figures are quoted as those organisations
  reported them.
