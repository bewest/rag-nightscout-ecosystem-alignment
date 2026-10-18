# Why organise: an accountable party for the ecosystem, and why now

*What this is: a proposal (part 3 of the overview, recommendations; [how the overview is organised](README.md)), for the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community. Read after [partner readiness](PARTNER-READINESS.md); leads to [the work itself](README.md#the-work-itself), starting with [reviewer onboarding](REVIEWER-ONBOARDING.md). **DRAFT PROPOSAL for discussion.** Living page, written 2026-10-17. It draws together evidence from
[partner readiness](PARTNER-READINESS.md), [what we believe, and how it works](perspective/PROCESS-MODELS.md),
the [vendor note](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md) and the
[evidence page](observations/ECOSYSTEM-EVIDENCE.md). Its characterisations of law are drafts for the
foundation's counsel, and of regulation for a regulatory professional, before anything rests on
them (§9). Nothing here is decided.*

*Author's interests: the author maintains cgm-remote-monitor, founded a company that hosts
Nightscout commercially, and could be a candidate for paid work under the related proposals. The
[collaboration rules](COLLABORATION-MODEL.md) §5 would apply to that company and to the author like
anyone else.*

## 1. The claim

Open-source diabetes software reaches devices and vendor clouds today through routes that no one in
the ecosystem is accountable for and no one can renew. Newer devices move the key to the
manufacturer, and access has already been lost or delayed for whole device generations. Every
route that could replace today's, for more than one person or for any command, needs a party that
can sign an agreement, take complaints, hold insurance and answer for a service. No such party
exists in the ecosystem today. Organising one takes years, and the dates that matter fall in 2027.

## 2. How access works today

The [access ladder](perspective/PROCESS-MODELS.md#1access-paths-who-holds-the-key-on-each-path)
places each device line by how much an open app depends on its manufacturer. Each placement was
read in the drivers' code on 2026-10-17 and is recorded in
`tools/structure-diagrams/access/devices.yaml`.

| step | what an open app needs | device lines | who is accountable for the access |
|---|---|---|---|
| A | the protocol, plus what the person has: a code, a serial, the device itself | Omnipod Eros and DASH, Medtronic 5xx/7xx, Tandem t:slim X2 and Mobi, Dana RS/i, Medtrum Nano, Dexcom G6, Libre 1/2, Eversense E3, Accu-Chek SmartGuide | no one; the protocol was worked out by volunteers |
| B | the manufacturer's own app running alongside | G7 passive mode, Medtronic 640G/670G and several CGMs through companion apps | no one; it lasts while the manufacturer's app tolerates it |
| C | a credential through the person's own account | Eversense 365 | the manufacturer's service, at its discretion |
| D | the device checks the app | Dexcom G7, Libre 3, MiniMed 780G, Omnipod 5 | no one; open apps present credentials the manufacturer did not issue to them |
| E | readings sealed for the manufacturer's cloud | none found; not looked for | — |

Open Omnipod 5 support currently depends on a community-run certificate service. A service that
therapy depends on needs a named operator, a contract, insurance and a successor
([programme §2b](ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating)).

Beside the devices, the vendor-cloud path that Nightscout's connectors use logs in as the person,
under terms that ban unauthorised apps, and it breaks when the cloud changes
([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)).
The legal cover in the US is the copyright exemption for device data: a defence for data access
only, renewed every three years, which does not cover commands or the distribution of
circumvention tools ([vendor note §3.4](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#34-dmca-1201-exemptions-37-cfr-20140)).

What each path's loss would mean, for the person and for caregivers, is in
[partner readiness §1](PARTNER-READINESS.md#what-is-at-stake-on-each-path).

## 3. Access already lost or delayed

The [access-loss log](../60-research/structures-2026-10-17/access-loss-log-2026-10-17.md) dates 34
events from public commits, issues and vendor pages: 11 on devices and 23 on vendor clouds.

**Devices.**

- **Medtronic pumps after the Paradigm series were never openly controllable.** The 530G (2013),
  the 600 series (read only, through companion apps or CareLink) and the 770G/780G have no open
  control driver; the 780G work that began in 2026 is a proof of concept "not for therapy". The
  openly controllable Paradigm family was the subject of an FDA cybersecurity communication in
  2019 that recommended replacing it (read through press coverage).
- **Access to newer generations arrived years late, through volunteer reimplementation.** From
  clearance or first launch to open support:
  - Omnipod DASH: 32 months to the first AndroidAPS code, 55 months to a Loop release.
  - Dexcom G7: 5 months to direct pairing in xDrip+, 47 months to Loop's development branch. Loop
    and Trio releases still listen alongside Dexcom's app.
  - Libre 3: up to 27 months, on Android.
  - Omnipod 5: 49 months, on a development branch only.
- **Some routes were removed.** Abbott sent GitHub takedown notices for patched-app projects in
  2019 (two), 2021 and 2023 (two).

**Vendor clouds.**

- **23 breakages since 2020**: LibreLinkUp 8, Tandem 6, CareLink 4, Dexcom Share 3, Glooko 1,
  and Dexcom's channel to Sugarmate 1. Eleven were fixed in at least one connector within seven
  days. Five are unfixed or only partly mitigated, including CareLink's move to a new sign-in
  that blocks automated logins (2026). Nightscout's own connector took 11 months to follow
  LibreLinkUp's October 2025 change that another connector met before the deadline, and its
  Glooko source was broken for about 15 months.
- **The one restoration that came through an agreement went to a company.** When Dexcom closed
  the channel Sugarmate used in November 2021, Sugarmate's data came back through Dexcom's
  partner API within weeks in the US. Its Nightscout bridge, which had no agreement, never came
  back.
- **The next change is already shipping.** LibreLinkUp's app 5.0 (April 2026) uses a new
  interface whose responses connectors cannot read. The older interface still works, and no date
  for switching it off has been found.

No source records how many people any of these events reached (§8).

## 4. Where newer devices are going

Manufacturers' own systems are moving setup online. From their public documents, read 2026-10-17
([cloud-pairing census](../60-research/structures-2026-10-17/cloud-pairing-census-2026-10-17.md)):

- **Every phone app read for a current CGM line needs a manufacturer account at first setup**:
  Dexcom, Abbott, Eversense, Roche and Sibionics. Dedicated receivers and readers are documented
  without one. On the pump side, the MiniMed Mobile, Tandem, Omnipod 5 and CamAPS FX (YpsoPump)
  apps and controllers also start with an account sign-in.
- **Three lines say the setup or pairing step itself needs the internet**: Dexcom ONE+, Eversense
  365, and CamAPS FX.
- **One manufacturer documents a credential its app delivers for another's device.** Beta Bionics'
  iLet app "loads certificates required to enable Dexcom G7 features"; where they come from is not
  stated. A partner's product meets the G7 app check with certificates its own app loads; open
  software meets the same check with a credential no one issued to it (§2).

What a manufacturer's app needs at setup does not decide whether an open app can reach the device:
"account at setup" appears on step A and step D alike. What the record shows is the direction:
accounts and online steps at setup, and app checks met by partners through issued certificates.
How many devices still on sale sit on step A, and for how long, is not known (§8).

## 5. Every replacement route needs an accountable party

| route | what it requires | for whom it works |
|---|---|---|
| a written agreement with a manufacturer (tiers A–C, [partner readiness §2](PARTNER-READINESS.md#2-three-tiers-of-access-and-which-to-ask-for-first)) | a legal entity, named contacts, security response, complaint handling, insurance, and terms both sides sign ([§3–§5](PARTNER-READINESS.md#3-what-a-manufacturer-will-need-to-see)) | everyone the agreement covers |
| the FDA's interoperable routes (iCGM, ACE pump, iAGC) | a manufacturer with a quality system, and contracts that assign complaint duties ([vendor note §2](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#2-regulatory-interoperability-fda)); Tidepool, a non-profit, took this route from 2020 to 2023 ([precedents](perspective/PRECEDENTS.md#tidepool-loop-20202023)) | users of the cleared product |
| credentials issued under the manufacturer's authority | an operator with its own contract, security controls, insurance and successor ([partner readiness §7](PARTNER-READINESS.md#7-credentials-for-devices-that-require-them)) | everyone the operator serves |
| a vendor's published developer route | Dexcom's is the only one found: a registered developer, five people for an individual, a non-negotiable agreement beyond that, and readings one to three hours late ([vendor note §1.2](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#12-dexcom)) | display and research; not automated insulin delivery |
| an EU Data Act request by a third party the person names | an organisation that meets Art. 6's conditions and the GDPR ([vendor note §5.3](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#53-what-an-organisation-would-need-to-use-each-right)) | EU users; data only |
| an EU Data Act request by the person for their own data | nothing institutional | one person at a time, in the EU; data only; untested for CGM data |

The last row is the one route that needs no organisation, and it carries data only, in one
jurisdiction. The requirements in the other rows are the same for anyone who meets them; a
non-profit has no advantage in meeting them
([what each activity brings §5](perspective/ACCOUNTABILITY-THRESHOLDS.md#5-the-same-requirements-for-anyone)).

## 6. Why now

| when | what | what it means for access |
|---|---|---|
| to 2027-10-28 | the 10th triennial rulemaking decides whether the device-data exemption continues ([vendor note §3.4](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#34-dmca-1201-exemptions-37-cfr-20140)) | renewal comments are stronger with dated, counted cases (§3); none are recorded in that form today |
| since 2026-09-12 | the EU Data Act's design duty for connected products placed on the market from that date ([vendor note §3.1](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#31-eu-data-act)) | devices launching now are the first that must be designed for access; the right is untested for diabetes data |
| early 2027 | Apple requires health apps to declare whether they are a regulated device ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)) | reaches every person who builds an app under their own developer record |
| 2027 | Android developer verification extends to all installs ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)) | reaches every AndroidAPS and xDrip+ builder |
| 2026–2027 | MiniMed separated from Medtronic (2026-10-15); Diabeloop's algorithm on twiist for a 2027 US launch ([vendor note §1.4, §1.7](../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#14-minimed-medtronic-diabetes)) | partner terms are being set between companies now |
| lead time | the one regulated route a community project took ran 2020–2023 | a start in 2026 lands near 2029 |

*Interpretation.* None of these dates is a crisis on its own. Together with §2–§4 they mean that
the routes in §5 take longer to open than the routes in §2 are likely to last, and the dates by
which evidence and an accountable party would help fall in 2027.

## 7. What organising means here

Organising does not mean the foundation running devices' credentials or anyone's therapy. The
proposals already before the board divide the work by role:

- **The foundation sponsors and oversees.** It pays for, convenes and sets the rules for shared
  work, and operates a service only by a recorded decision that names the operator, its contract,
  its insurance and its successor ([programme §2b](ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating)).
  A credential service needs an operator of its own; issuance has standing only under the
  manufacturer's authority ([partner readiness §7](PARTNER-READINESS.md#7-credentials-for-devices-that-require-them)).
- **An accountable counterparty signs.** A manufacturer agreement needs a legal entity with named
  contacts, security response, complaint handling and insurance. In practice that is usually a
  company; the foundation's role is the oversight layer above it
  ([what each activity brings §5](perspective/ACCOUNTABILITY-THRESHOLDS.md#5-the-same-requirements-for-anyone);
  drawn in [2·agreement and 2·controller-operator](perspective/STRUCTURES.md)).
- **The projects keep their code and their roadmaps.** Paying for shared work buys no control
  over any project ([collaboration rules](COLLABORATION-MODEL.md) rule 2).

The steps that cost little and produce the evidence the rest depends on can start now
([partner readiness §8](PARTNER-READINESS.md#8-order-of-work)):

1. a shared intake that records each access loss: the device or cloud, the date, how long it
   lasted and how many people and projects it reached;
2. a security contact and private vulnerability reporting for each project;
3. one EU Data Act request, made by a person for their own real-time CGM data, to learn how a
   manufacturer answers;
4. one tier A request to one manufacturer, to learn what it requires;
5. the readiness dossier of partner readiness §3, kept current.

An accountable counterparty, its insurance, and any agreement follow from what those steps show.

## 8. What this page does not show

- **When today's open devices leave supply.** End-of-sale and coverage dates for the step A
  devices have not been collected. They set how long the routes in §2 last.
- **How many people each loss reached.** No outage has been counted (§7, step 1).
- **Whether manufacturers would agree.** No request by the foundation or the projects is on record;
  whether one was ever made should be confirmed with the maintainers.

## 9. Points for reviewers to verify

- The law in §2, §5 and §6 is summarised from the vendor note; its own review points (vendor note
  §7) apply here, in particular the device-data exemption's scope (points 6, 7 and 16) and the Data
  Act's reach to CGM data (points 1–4).
- The step placements in §2 were read in code, not run against devices.
- The dates in §6 come from the evidence page and the vendor note; re-read them before the page is
  quoted outside the ecosystem.
