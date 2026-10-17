# Vendor programmes and data rights: what is open, to whom, and under what law

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Research note, 2026-10-17.** Every external fact below carries its source and was read on
2026-10-17 unless it says otherwise. Facts carried over from the
[cloud-layer census](../programme/stack-census-2026-09-30/cloud-layer.md) were read on 2026-09-30
and say so. Anything that could not be checked against a primary source is marked **not
verified**.*

*Draft for legal review. This note is not legal advice. Wherever it describes what a statute,
regulation, contract or terms of use says or how it might apply (§3, §4 and the tables in §5), it is
a non-lawyer's reading for review by the foundation's counsel, and the FDA items also by a
regulatory professional, before anyone relies on them. The specific points for a reviewer are
listed in §7.*

It adds to [DIGITAL-RIGHTS](../../DIGITAL-RIGHTS.md) (rights that do not depend on a
manufacturer's permission), the [data rights primer](../../10-domain/data-rights-primer.md) (the five
rights: access, export, share, delegate, audit), [PARTNER-READINESS](../../00-overview/PARTNER-READINESS.md)
(tiers A, B and C of access; what an agreement must carry) and the cloud-layer census §2 (documented
routes out of vendor clouds, and the FDA and data-law texts read on 2026-09-30). It does not repeat
them. Apple's developer tiers are covered in the sibling note
[apple-accountability](apple-accountability.md); device-protocol facts come from the
[device-layer census](../programme/stack-census-2026-09-30/device-layer.md), at mechanism level only.

## Terms used

| term | meaning here |
|---|---|
| **API** | application programming interface: a documented way for one program to ask another for data |
| **OAuth** | a login pattern in which a person approves an app's access on the vendor's own page, and can later withdraw it, without giving the app their password |
| **sandbox** | a test copy of a vendor's API that returns made-up data |
| **real-time / delayed** | real-time means each reading is available within minutes of the sensor taking it; delayed means a fixed lag (for example one hour) or upload in batches |
| **iCGM, ACE pump, iAGC** | FDA device types for a CGM, an insulin pump and a dosing algorithm that are cleared to work with each other's kind from other manufacturers (21 CFR 862.1355, 880.5730, 862.1356) |
| **interface specification** | the technical description of how another device or program may talk to a device |
| **special controls** | the conditions FDA attaches to a device type, which every device of that type must meet |
| **connected product, data holder, user, third party** | EU Data Act terms: the device; the company that holds its data (often the manufacturer running the cloud); the owner or person using it; and anyone the user asks the data holder to send the data to |
| **TPM / circumvention** | technological protection measure (for example encryption or authentication) and getting around it; §1201 of the US copyright law forbids circumvention unless an exemption applies |
| **trafficking** | offering a tool to the public whose main purpose is circumvention; §1201(a)(2) forbids it, and the triennial exemptions do not cover it |

## 1. Vendor programmes

Read from each vendor's own pages unless marked. "Who may join" means what the page says; where it
says nothing, the cell says "not stated".

### 1.1 Summary

| vendor | published programme for outside developers? | who may join | access | real-time? | sandbox | fees | restrictive terms found | review step |
|---|---|---|---|---|---|---|---|---|
| Dexcom | **yes**: developer API (v3) | individuals (Limited Access, up to 5 users); companies (commercial partnership); non-profits not stated | OAuth; six read-only endpoints; scopes all or nothing | **no** in the public API: 1 h delay in the US, 3 h elsewhere; a separate real-time "Partner Web API" is by invitation | yes | not stated | non-negotiable Data Licensing Agreement (text not public); consumer terms forbid automated access and "unauthorized third-party applications" | Dexcom Strategic Partnerships review; app-by-app |
| Abbott | **nothing published found** for outside developers; a partner list exists | not stated | partner integrations only | not stated | no | not stated | consumer terms not read (§1.3) | "evaluated by Abbott Diabetes Care" |
| MiniMed (formerly Medtronic Diabetes) | **nothing published found** | — | CareLink Connect (care partners, up to five), clinic upload | — | — | — | — | — |
| Tandem | **nothing published found** for developers; FDA records describe a contractual plan for connected-device companies (§2) | — | Tandem Source with a user-authorised link to Glooko | **no**: "do not happen in real time" | no | — | — | — |
| Insulet | **nothing published found** | — | partner integrations (CGM makers, Glooko, LibreLinkUp cloud link) | — | — | — | — | — |
| Roche | **partner-only** sandbox for EMR/PHR systems | partners; onboarding through Roche | mutual-TLS API (FHIR implementation guide) | not stated | yes (partners) | not stated | not read | onboarding not described |
| Ypsomed (mylife) | **nothing published found** | — | named partnerships (CamDiab, Dexcom, Abbott) | — | — | — | — | — |
| Sequel (twiist) | **nothing published found** | — | partner algorithms (Tidepool Loop now; Diabeloop announced) | — | — | — | — | — |
| Medtrum | **nothing published found** | — | — | — | — | — | — | — |
| Tidepool (non-profit platform) | **yes**: published API | anyone may request a client identifier | OAuth partner integrations; data upload and read | not stated | separate integration environment | not stated | not read | client id on request |

### 1.2 Dexcom

- **Developer API.** Registered developers get six read-only endpoints (alerts, calibrations,
  dataRange, devices, egvs, events) for G6, G7, G7 15-day, ONE and ONE+. Data from the phone apps is
  "available from the Dexcom API with a one-hour delay in the United States", three hours outside;
  data uploaded from a receiver over USB is available at once.
  <https://developer.dexcom.com/docs/dexcomv3/endpoint-overview/>
- **Tiers.** Sandbox with four simulated users, not to be used "for formal testing, validation, or
  training algorithms" (<https://developer.dexcom.com/docs/dexcom/sandbox-data/>); **Limited
  Access**, which an "Individual" may apply for and which allows "up to 5 authorized users"; **Full
  Access**, for which commercial developers "must submit a request for a commercial partnership".
  <https://developer.dexcom.com/docs/dexcom/scopes-access/> ,
  <https://developer.dexcom.com/docs/dexcom/getting-started/>
- **Review and terms.** "Dexcom Strategic Partnerships team will review your application"; Dexcom
  may require technical and interface changes; "you will be sent a standard, non-negotiable Data
  Licensing Agreement". The agreement's text is not public (**not verified**: whether it restricts
  therapeutic or dosing use). There is "currently no way for developers to request a subset of these
  scopes". Same page.
- **Revocation.** "Users can revoke their authorization at any time at Dexcom.com"; Dexcom then stops
  sending data, but "any information previously provided to the developer's app will not be affected
  by this revocation". Same page. Revocation of a developer by Dexcom: not described.
- **Real-time partners.** FDA cleared the "Dexcom Partner Web APIs" in July 2021 for "invited
  third-party developers"; Garmin and Teladoc's Livongo were named
  (<https://www.biospace.com/fda-clears-dexcom-real-time-apis-for-third-party-apps-and-devices>,
  a trade report of the 2021-07-15 press release; Dexcom's own release returned 403). Dexcom's
  developer pages read today do not describe a real-time tier or how to be invited.
- **Partner pages.** Dexcom says it integrates with "over 90 connected health apps" and pumps, and
  links a "Partnership Interest" intake form; no criteria are published.
  <https://www.dexcom.com/partnerships/integrations-and-compatibility>
- **Consumer terms** (effective 2023-01-26), §5.11: users may not "use any automated process or
  service (such as a bot, a spider, or periodic caching of information)", "copy or scrape data from
  any DexCom Product", "reverse engineer or derive the source code", or "enable unauthorized
  third-party applications to access DexCom Products or DexCom Services".
  <https://www.dexcom.com/en-us/legal/terms-of-use>

### 1.3 Abbott

- **Partner list, not a programme.** Abbott's integrations page lists the MiniMed 780G, MiniMed Go
  and MiniMed Flex (with the Instinct sensor Abbott makes), NovoPen 6 and Echo Plus, mylife Loop
  (CamAPS FX with YpsoPump), Omnipod 5, a LibreLinkUp–Omnipod 5 cloud connection, Tandem t:slim X2,
  Beta Bionics iLet, "twiist AID System Powered by Tidepool" and Omada Health. "This list will be
  updated as other devices, apps, software, and systems are evaluated by Abbott Diabetes Care." It
  warns that use with devices "that are not listed may cause inaccurate glucose readings". No
  developer programme, API or SDK is mentioned.
  <https://www.diabetescare.abbott/partnerships/integrations/en.html>
- **Data aggregators.** One aggregator documents two routes: the person's LibreView login, which "is
  no longer supported for new connections", and the person sharing their account with the
  aggregator's LibreView *practice* (clinic) account, so that it "accesses the patient CGM data as a
  member of the LibreView practice". <https://docs.junction.com/wearables/guides/abbott-libreview>
  (an aggregator's page, not Abbott's; Abbott's own terms for practice accounts were not read).
- **Consumer terms** for LibreLink and LibreLinkUp: **not read**; the search did not return them.
  The census records that LibreLinkUp terms prompts block connectors until the person accepts them
  (cloud-layer §1.3, Nocturne `828b25ce`).

### 1.4 MiniMed (Medtronic Diabetes)

- **Corporate change.** MiniMed Group, Inc. completed its separation from Medtronic plc on
  2026-10-15 (8-K exhibit,
  <https://www.sec.gov/Archives/edgar/data/0002062583/000110465926116441/tm2627653d1_ex99-1.htm>,
  read through a search summary, **not verified** in full). Repository pages that say "Medtronic
  CareLink" now refer to a MiniMed service.
- **Sharing routes.** The current support page lists automatic upload to the care team's CareLink
  Clinic and the CareLink Connect app to "share your MiniMed pump and sensor data along with the
  system alerts with up to five care partners". It names no third-party app, export file or API.
  <https://www.minimed.com/en-us/support/product-support/minimed-flex/sharing-your-data>
- **Interoperability.** Medtronic announced on 2025-09-02 that FDA cleared the SmartGuard algorithm
  as an iAGC so the 780G can use the Instinct sensor, the 780G having been cleared earlier as an ACE
  pump (<https://news.medtronic.com/2025-09-02-FDA-Clears-MiniMed-TM-780G-System-to-Enable-Integration-with-the-Instinct-Sensor,-Made-by-Abbott,-and-Approves-Use-in-Type-2-Diabetes>,
  read through a search summary).
- Looked for and **nothing published found**: a developer or partner API page on minimed.com or
  medtronicdiabetes.com.

### 1.5 Tandem

- **Tandem Source** "is not intended for use as a remote monitoring tool for caregivers" and "Data
  uploads to the Tandem Source platform do not happen in real time." No partner is named.
  <https://www.tandemdiabetes.com/support-center/pumps-and-supplies/cartridges/article/data-sharing-capability-tandem-source>
- Glooko documents a user-authorised link from Tandem Source (cloud-layer §2.1, 2026-09-30).
- **ACE pump.** Tandem's FDA decision summary for the first ACE pump (DEN180058) records a plan
  covering "their approach to working with connected device companies regarding contractual
  approaches, interfaces for data communication and exchange, and post-market reporting procedures
  and responsibilities (e.g., who is responsible for investigating and reporting complaints,
  malfunctions, and adverse events)". <https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN180058.pdf>
- Looked for and **nothing published found**: a page on tandemdiabetes.com describing how a third
  party may apply for the interface specification or integrate a controller.

### 1.6 Insulet (Omnipod)

- The innovation page says Omnipod 5 "works with leading sensor brands" and names Dexcom and Glooko
  as trademark licensors; it mentions no third-party algorithm, developer programme or API.
  <https://www.omnipod.com/innovation>
- A 2023 Tidepool reading of Insulet's Omnipod 5 decision summary found "plans covered Insulet's
  approach to working with third party manufacturers of digitally connected devices" and the 510(k)
  statement "Future alternate controllers (iAGCs) may be established for use with the Pod"
  (<https://www.tidepool.org/blog/the-inside-scoop-on-third-party-control-for-ace-pumps>,
  2023-02-01; the Insulet summary itself was **not read**).
- Device level: the Omnipod 5 driver in the community kit uses message signing with a certificate
  store and an Apple App Attest service (device-layer census, OmnipodKit row). App Attest is Apple's
  service by which an app proves to a server that it is a genuine, unmodified build; this is the
  "credential the manufacturer issues" case in PARTNER-READINESS §1 and §7.
- Looked for and **nothing published found**: a developer, partner or interface-specification page on
  omnipod.com or insulet.com.

### 1.7 Roche, Ypsomed, Sequel, Medtrum

- **Roche.** Roche Diabetes Care publishes an EMR implementation guide with a "Sandbox API to allow
  EMRs, PHRs and other systems test certain features" without "full scale onboarding", using
  mutual-TLS certificates Roche provides (<https://simplifier.net/guide/RDCEMRImplementationGuide/sandboxapi>).
  Glooko announced on 2026-03-10 that it will be "the first diabetes data management platform outside
  of Roche's ecosystem" to integrate the Accu-Chek SmartGuide CGM (search summary of
  <https://www.businesswire.com/news/home/20260310206611/en/Glooko-to-Expand-EMEA-CGM-Connectivity-with-Roche-Accu-Chek-SmartGuide-Integration>).
  A UK report says newly activated SmartGuide sensors will pair "exclusively with the mySugr app"
  after a transition (<https://www.disn-uk.co.uk/news/roche-diagnostics-accu-chek-smartguide-users-to-transition-to-mysugr-app>,
  search summary, **not verified** with Roche).
- **Ypsomed.** Partnerships with CamDiab (CamAPS FX on YpsoPump) and Dexcom are published as press
  releases (<https://www.ypsomed.com/en/media/details/ypsomed-partners-with-camdiab-ltd-to-drive-on-smartphone-based-adaptive-automated-insulin-delivery-aid.html>).
  A 2018 JDRF-funded project aimed at "open-protocol communication" for the next YpsoPump
  (<https://www.jdrf.org/?p=26795>); whether it reached regulatory approval was **not verified**.
  **Nothing published found** for a developer programme or mylife Cloud API.
- **Sequel (twiist).** Tidepool says Tidepool Loop is distributed "as a licensed, third-party
  distributed product, most recently through Sequel Med Tech as twiist Loop" (<https://www.tidepool.org/>).
  Diabeloop announced on 2026-01-13 that its DBLG2 algorithm, cleared as an iAGC on 2025-12-18, will be
  integrated into twiist, with "product readiness by end of 2026 and launch in the US in 2027"
  (<https://www.diabeloop.com/news/company/dbl-sequel-partnership-en>). **Nothing published found**
  for a developer programme.
- **Medtrum.** medtrum.com links consumer apps, a compatible-devices page and a clinician portal;
  **nothing published found** for a developer or partner programme
  (<https://www.medtrum.com/>; a web search returned nothing relevant).

### 1.8 Tidepool

- **Platform.** Tidepool's API "not marked Internal" is "available to everyone", a client identifier
  must be requested, and there are separate integration and production environments (cloud-layer
  §2.1, 2026-09-30). Its public code shows OAuth partner integrations with the Dexcom developer API,
  Abbott (through a private plugin), twiist and Oura (cloud-layer §1.1).
- **Tidepool Loop.** Tidepool describes Tidepool Loop as built on the community Loop app and taken
  through FDA; its device-partners page names no partner other than twiist and states no licensing
  terms or partner requirements (<https://tidepool.org/loop-device-partners>).
- **CMS pledge.** "Tidepool Project" is listed among the pledgees in the US Centers for Medicare &
  Medicaid Services (CMS) Health Tech Ecosystem "Diabetes and Obesity" category, whose pledge is to
  "connect to CMS Aligned Networks or personal health apps and, with patient consent, securely access
  relevant health data". No CGM or pump manufacturer appears on that page.
  <https://www.cms.gov/health-tech-ecosystem/early-adopters/diabetes-obesity> (page last modified
  2026-08-06). The initiative is voluntary
  (<https://www.cms.gov/newsroom/press-releases/white-house-tech-leaders-commit-create-patient-centric-healthcare-ecosystem>).

### 1.9 Where the vendor routes leave the ecosystem

Read together with the census: the only published self-service route to CGM data from a
manufacturer is Dexcom's, and it is delayed by one to three hours, capped at five people for an
individual developer, and gated by a non-negotiable agreement for anything larger. Every
real-time route a manufacturer offers is by invitation or bilateral contract. No pump manufacturer
publishes a developer route at all. The ecosystem's real-time data still comes from follower
services and device protocols that the vendors do not document (cloud-layer §2.1, last paragraph).

## 2. Regulatory interoperability (FDA)

The special-controls text of 21 CFR 862.1355 (iCGM), 880.5730 (ACE pump) and 862.1356 (iAGC) is
quoted in cloud-layer §2.2. New since then:

- **What the decision summaries say a manufacturer must plan.** The first ACE pump (DEN180058) and
  first iAGC (DEN190034) summaries both record that the sponsor's plan was found adequate "to
  support and clearly specify expectations, requirements, and interface specifications to potential
  interoperable devices", and covered contracts, data interfaces and "post-market reporting
  procedures and responsibilities (e.g., who is responsible for investigating and reporting
  complaints, malfunctions, and adverse events)" (DEN190034 says "contractual issues").
  <https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN180058.pdf> ,
  <https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN190034.pdf>. The FDA record therefore expects
  interface specifications to reach other manufacturers **through contracts that allocate complaint
  handling**, which is the shape PARTNER-READINESS §5 and §6 already anticipate.
- **No published route for a third party.** No manufacturer page read for §1 describes how a third
  party may request its interface specification. Tidepool's 2023 reading was that the special
  controls "do not require that the pump manufacturer provide plans for how their pump can
  communicate with any controller" (blog cited in §1.6).
- **Cross-maker combinations are now common.** FDA clearances and announcements since 2019 have
  produced pump–sensor–algorithm combinations across manufacturers: Abbott's list in §1.3; the 780G
  with Instinct; Diabeloop's iAGC on twiist. Each was made by a company contracting with another.
- **FDA statements on third-party interoperability.** FDA's 2019 announcement of the first iAGC was
  titled as "designed to allow more choices for patients"; the fda.gov page returned 404 and is
  **not verified**. FDA's guidance "Design Considerations and Pre-market Submission Recommendations
  for Interoperable Medical Devices" is cited in both decision summaries. No newer FDA statement on
  interoperability with non-manufacturer software was found.

## 3. Data-rights and blocker-removal law

| instrument | applies from | scope, in short | reaches CGM/pump data or vendor clouds? |
|---|---|---|---|
| EU Data Act, Reg. (EU) 2023/2854 | 2025-09-12; design duty (Art. 3(1)) for products placed on the market after 2026-09-12 | users of connected products and related services in the EU; access, and sharing with a third party the user chooses | plausibly yes, in the EU (§3.1) |
| European Health Data Space, Reg. (EU) 2025/327 | 2027-03-26, rights in stages 2029 and 2031 (census) | access to health data held by healthcare providers' EHR systems | indirectly; not vendor clouds (§3.2) |
| US information blocking, 45 CFR 171 | in force | providers, certified health IT developers, networks and exchanges | not device makers as such (§3.3) |
| DMCA §1201 exemptions, 37 CFR 201.40 | 2024-10-28 to 2027-10-28; renewal under way | circumvention to access one's own device data; device repair; phone jailbreaking | yes for data access; not for control (§3.4) |
| FTC Health Breach Notification Rule, 16 CFR 318 | amended 2024 | breach notice by health apps and PHR vendors outside HIPAA | an obligation, not an access right (§3.5) |
| Washington My Health My Data Act, RCW 19.373 | 2024-03-31 | consumer health data of Washington residents | access and deletion rights; obligations on recipients (§3.6) |
| Right-to-repair laws | various | parts, tools, documentation | medical devices excluded where checked (§3.7) |
| EU Digital Markets Act Art. 6(7) | decisions March 2025 | Apple must open iOS connectivity features to third-party devices in the EU | the phone, not the medical device (§3.8) |

### 3.1 EU Data Act

Text read from the Official Journal copy at <http://publications.europa.eu/resource/celex/32023R2854>
(EUR-Lex returned a bot challenge on 2026-09-30, so the Publications Office copy was used).

- **Dates (Art. 50).** "It shall apply from 12 September 2025." The Art. 3(1) design obligation
  applies "to connected products and the services related to them placed on the market after
  12 September 2026". Chapter IV (unfair contract terms) applies to contracts concluded after
  2025-09-12, and from 2027-09-12 to some older long contracts.
- **The user's own access (Art. 4(1)).** Where data cannot be read directly from the product, the
  data holder must make "readily available data" accessible "without undue delay, of the same quality
  as is available to the data holder, easily, securely, free of charge, in a comprehensive,
  structured, commonly used and machine-readable format and, where relevant and technically
  feasible, continuously and in real-time". A contract term that excludes or varies the user's
  rights "shall not be binding on the user" (Art. 7(2)). This right does not need a third party: a
  person could receive their own data into a tool they run themselves (Recital 22 mentions
  processing "within an information and communications technology (ICT) environment chosen by the
  user").
- **Sharing with a third party the user chooses (Art. 5(1)).** "Upon request by a user, or by a party
  acting on behalf of a user", the data holder must make the same data available to a third party,
  "free of charge to the user", "continuously and in real-time" where relevant and feasible. The
  data holder may charge the third party "reasonable" compensation (Art. 9(1)); where the recipient
  is an SME (small or medium-sized enterprise) "or a not-for-profit research organisation", it may
  not exceed the cost of making the data available (Art. 9(4)).
- **Gatekeepers excluded (Art. 5(3), 6(2)(d)).** Companies designated as gatekeepers under the
  Digital Markets Act (Apple, Google and others) may not be the third party, and a third party may
  not pass the data to one.
- **What a third party must accept (Art. 6).** Use only "for the purposes and under the conditions
  agreed with the user"; erase when no longer needed; no profiling unless needed for the service;
  no onward sharing except by contract with the user; not use the data "to develop a product that
  competes with the connected product from which the accessed data originate"; not use it "in a
  manner that has an adverse impact on the security of the connected product".
- **Carve-outs a manufacturer can use.**
  - *Security and health (Art. 4(2)).* Access or sharing may be contractually restricted "if such
    processing could undermine security requirements of the connected product, as laid down by Union
    or national law, resulting in a serious adverse effect on the health, safety or security of
    natural persons". A refusing data holder must notify the national competent authority.
  - *Trade secrets (Art. 4(6)–(8), 5(9)–(11)).* Disclosure under confidentiality measures; withholding
    if measures are not agreed; refusal "in exceptional circumstances" where serious economic damage
    is "highly likely". Each refusal must be reasoned in writing and notified to the authority, and
    can be challenged (Art. 4(9), 5(12)).
  - *Derived data (Recital 15).* Information "inferred or derived ... by means of proprietary, complex
    algorithms" is outside scope. Whether a CGM's glucose value (computed by the manufacturer's
    algorithm from the sensor signal) is "pre-processed" (in scope) or "derived" (out) is the
    single most consequential open question for diabetes (§7).
- **What it does not do.** The user and third party "shall not use coercive means or abuse gaps in
  the technical infrastructure of a data holder which is designed to protect the data in order to
  obtain access" (Art. 4(11), 5(5)). The Act is "without prejudice to" intellectual-property law,
  including the EU copyright directive that carries the anti-circumvention rule (Art. 1(8)). It
  gives a right to **ask** and a complaint route (Art. 37), not a licence to reverse-engineer.
- **Medical devices.** Recital 14 lists "medical and health devices" among connected products, and
  the Commission FAQ (v1.4, 2026-01-22, still the latest listed on
  <https://digital-strategy.ec.europa.eu/en/library/commission-publishes-frequently-asked-questions-about-data-act>)
  says the Act "applies to all connected products, including those that are subject to specific type
  approval or conformity assessment regimes (e.g. ... medical devices)" (cloud-layer §2.2).
- **Pending change.** The Commission's "digital omnibus" proposal includes Data Act amendments.
  Secondary reports say the data part had not reached trilogue (negotiation between Parliament and
  Council) by late 2026 (**not verified**; procedure 2025/0360(COD) should be checked).
- **Small manufacturers.** Chapter II does not apply to micro and small enterprises that are not
  linked to larger ones (Art. 7(1)).

### 3.2 European Health Data Space

Read from <http://publications.europa.eu/resource/celex/32025R0327>. People get a right to access
"at least" the priority categories (patient summaries, prescriptions, images, results, discharge
reports) "processed for the provision of healthcare" through national access services (Art. 3), with
proxy services so a person can authorise another person (Art. 4(2)), and portability between
healthcare providers (Art. 7). Medical-device manufacturers that claim interoperability with EHR
systems must meet the EHR interoperability and logging requirements (Art. 27(1)). Device data reach
EHDS mainly as a secondary-use category, "personal electronic health data automatically generated
through medical devices" (cloud-layer §2.2). **Reading:** EHDS strengthens access to what a clinic
holds; it does not by itself oblige a CGM or pump cloud to share with a person's chosen tool.

### 3.3 US information blocking (21st Century Cures Act)

The actors are health care providers, developers of certified health IT, and health information
networks and exchanges; device makers are actors only if they hold certified health IT (cloud-layer
§2.2, 45 CFR 171.102). New since 2026-09-30: the HTI-5 proposed rule (published 2025-12-29, comments
closed 2026-02-27) would cut certification criteria and change some exceptions; no final rule was
found (search summaries of <https://www.mcdermottlaw.com/insights/astps-hti-5-relaxes-certification-criteria-while-tightening-information-blocking-exceptions/>
and healthit.gov materials, **not verified** against the Federal Register, whose API did not answer).

### 3.4 DMCA §1201 exemptions (37 CFR 201.40)

Current text read from eCFR
(<https://www.ecfr.gov/current/title-37/chapter-II/subchapter-A/part-201/section-201.40>):

- **(b)(7) medical device data:** "Literary works consisting of compilations of data generated by
  medical devices or by their personal corresponding monitoring systems, where such circumvention is
  undertaken by or on behalf of a patient for the sole purpose of lawfully accessing data generated
  by a patient's own medical device or monitoring system. Eligibility for this exemption is not a
  safe harbor from, or defense to, liability under other applicable laws, including without
  limitation the Health Insurance Portability and Accountability Act of 1996, the Computer Fraud and
  Abuse Act of 1986, or regulations of the Food and Drug Administration." The 2015 limits to
  implanted devices and passive monitoring are **not** in the current text.
- **(b)(17) medical device repair:** programs in "a lawfully acquired medical device or system ... when
  circumvention is a necessary step to allow the diagnosis, maintenance, or repair".
- **(b)(9) phones:** circumvention on smartphones and "portable all-purpose mobile computing devices"
  for "interoperability of such applications" or removal of software. It covers the phone, not the
  medical device.
- **Renewal (10th triennial rulemaking).** Notice of inquiry 2026-06-09; renewal petitions due
  2026-08-24; comments on them due 2026-09-28; renewed exemptions would run October 2027 to October
  2030 (<https://www.copyright.gov/1201/2027/>). The Coalition of Medical Device Patients and
  Researchers petitioned to renew (b)(7). The renewal page lists **no opposition** to (b)(7). It
  lists oppositions to the **repair** exemption (b)(17) from AdvaMed (the medical-technology trade
  association) and Philips, and a comment from the Joint Creators (games, film and music trade
  bodies) that does not oppose the exemption but addresses one petition
  (<https://www.copyright.gov/1201/2027/petitions/renewal/>; AdvaMed and Joint Creators filings read).
  No proposed rule had been posted on the read date.
- **Unchanged limits.** No exemption covers trafficking in circumvention tools (17 U.S.C.
  §1201(a)(2)), sending commands to a device, or breach of contract or terms of use.

### 3.5 FTC Health Breach Notification Rule (16 CFR 318)

From eCFR §318.2 (<https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-318>): a
"personal health record" is an electronic record "that has the technical capacity to draw
information from multiple sources and that is managed, shared, and controlled by or primarily for
the individual"; "health care services or supplies" include "any online service such as a website,
mobile application, or internet-connected device that provides mechanisms to track diseases, health
conditions"; a breach "includes an unauthorized acquisition ... that occurs as a result of a data
breach or an unauthorized disclosure". Vendors of personal health records and related entities must
notify people, the FTC and, for 500 or more people, the media
(<https://www.ftc.gov/legal-library/browse/rules/health-breach-notification-rule>). **Reading:** this
grants no access right; it is an obligation that a hosted service or a designated third party
outside HIPAA would probably carry.

### 3.6 State consumer health-data laws

Washington's My Health My Data Act (<https://app.leg.wa.gov/RCW/default.aspx?cite=19.373&full=true>):

- "Consumer health data" includes "Bodily functions, vital signs, symptoms, or measurements" of health
  status (RCW 19.373.010(8)(b)(v)).
- From 2024-03-31 a consumer may confirm and "access such data, including a list of all third parties
  and affiliates" it was shared with, withdraw consent, and have it deleted, with deletion passed on
  to every recipient (RCW 19.373.040).
- A "regulated entity" is "any legal entity" doing business in or targeting Washington; the
  definition does not exclude non-profits. HIPAA-protected health information is exempt
  (RCW 19.373.100). Violations are enforced through the state Consumer Protection Act (RCW 19.373.090).
- **Reading:** the access right is to confirmation, a copy and the recipient list; it does not
  require a machine-readable or real-time feed. It also places consent and deletion duties on any
  organisation that receives Washington residents' glucose data.
- Other states (for example Nevada and Connecticut) have related laws; **not read**.

### 3.7 Right to repair

- **Minnesota** (Stat. 325E.72, in force 2024-07-01): "Nothing in this section applies to
  manufacturers or distributors of a medical device as defined in the Federal Food, Drug, and Cosmetic
  Act" (<https://www.revisor.mn.gov/statutes/cite/325E.72>).
- **New York, Oregon, California, Colorado:** described by trade and advocacy sources as excluding or
  not reaching medical devices; statutes **not read**. Bills aimed at medical-device repair were
  pending in Vermont (H.160) and Rhode Island (H 7180) in 2026 (search results; **not verified**).
- **EU Right to Repair Directive** (EU) 2024/1799: its repair obligations reach only the products in
  Annex II (washing machines, dishwashers, refrigerators, displays, welding equipment, vacuum
  cleaners, servers, phones and tablets, tumble dryers, light-transport batteries); medical devices
  are not listed (<http://publications.europa.eu/resource/celex/32024L1799>).
- **Reading:** repair laws address parts and manuals, not data access; where checked, they exclude
  medical devices. The only repair route for diabetes devices found is the federal §1201 (b)(17)
  exemption, which industry is opposing in the current cycle.

### 3.8 Other jurisdictions and the phone

- **EU Digital Markets Act.** In March 2025 the Commission specified how Apple must give third-party
  connected devices access to nine iOS features in the EU, including background execution
  (all measures "no later than end of 2026"), notifications and proximity pairing (by 2026-06-01)
  (<https://digital-markets-act.ec.europa.eu/developer-portal/interoperability/apple-specification-proceedings-interoperability-connected-devices-and-request-based-process_en>).
  These concern the phone's treatment of accessories, which matters to apps that keep a Bluetooth
  link to a sensor or pump; they do not open the medical device. Apple's tiers and EU alternative
  distribution are in [apple-accountability](apple-accountability.md) §1.
- **UK.** Part 1 (smart data) of the Data (Use and Access) Act 2025 was commenced on 2025-08-20 (SI
  2025/904, search summary); it enables sector schemes by later regulations. No health or device
  scheme was found (**not verified**).

## 4. What is now out of date in the repository

| page | statement | what changed |
|---|---|---|
| DIGITAL-RIGHTS, "Medical Device Data Exemption" | "check the current wording of 37 CFR 201.40 for which limits remain" | the current (b)(7) text has no implanted-device or passive-monitoring limit (§3.4) |
| DIGITAL-RIGHTS, "The Next Rulemaking (2027)" | schedule to be checked | NOI 2026-06-09, petitions 2026-08-24, comments 2026-09-28; no opposition listed to (b)(7); AdvaMed and Philips oppose (b)(17) (§3.4) |
| DIGITAL-RIGHTS, §1201 notes | names security-research and interoperability exemptions but not (b)(9) | (b)(9) phone jailbreaking for app interoperability is renewed and petitioned again (§3.4) |
| DIGITAL-RIGHTS, "Data Portability Rights" | GDPR and state privacy laws only | the EU Data Act has applied since 2025-09-12, with real-time and third-party sharing duties and its own limits (§3.1) |
| DIGITAL-RIGHTS, "Right to Repair Landscape" ("As of January 2026") | "Medical devices are frequently exempted" | confirmed for Minnesota and the EU directive; the federal repair exemption is now opposed (§3.7) |
| data rights primer, "Relationship to Legal Frameworks" (Last Updated January 2026) | Access and Export rows list GDPR, state privacy, DMCA | add the Data Act (EU) and the Washington access right; Delegate row: the Data Act's "party acting on behalf of a user" and EHDS proxy services are the first legal forms of delegation found |
| cloud-layer census §2.1, Abbott row | partner table of four integrations | the list read today has eleven, including Tandem, Beta Bionics, twiist and Omada (§1.3) |
| cloud-layer census and other pages | "Medtronic CareLink" | MiniMed separated from Medtronic on 2026-10-15 (§1.4) |
| pages describing twiist as the Tidepool Loop product | — | Diabeloop's algorithm is to be integrated into twiist for a 2027 US launch (§1.7) |
| PARTNER-READINESS §9 question 10 | privacy regimes for complaint records | add the Washington act, which has no non-profit exclusion (§3.6) |

PARTNER-READINESS §5–§6 are **supported** by the FDA decision summaries in §2: the regulated route
already expects contracts that allocate complaint investigation and reporting.

## 5. Synthesis *(interpretation)*

### 5.1 Blockers, what is removing them, what still stands

| blocker | kind | what is removing it | what still stands |
|---|---|---|---|
| device encryption and pairing with a secret the person holds | technical | community implementations exist for most current devices (device-layer census, 14 protocols with two or more implementations), including authenticated pairing on Dexcom G7, Libre 3 and Tandem | each new protocol has to be worked out again |
| app attestation and manufacturer-issued client credentials | technical / commercial | none found for outsiders | found on Omnipod 5 (§1.6, read from the driver's file names); possibly SmartGuide "advanced security" variants (not determined; AccuChekKit `4f8c3a8` carries manufacturer-certificate code, all of it commented out). Eversense 365 takes a device certificate from the manufacturer's service through the person's own account, with no app check found (EversenseKit `e1bb6fa`); where a device checks that the app is a genuine build the manufacturer approved, only the manufacturer can grant access (PARTNER-READINESS §7), and nothing in law requires it to issue a credential to a non-partner |
| readings encrypted end to end between the device and the vendor's cloud | technical | none | not looked for in the census; where it is used, the phone relays data it cannot read and no reader on the phone, passive or authenticated, can use the readings |
| devices leaving supply | commercial | none | the devices open implementations support today leave sale and coverage over time; no dates collected (§6) |
| cloud access for real-time data | technical / contract | EU Data Act Art. 4–5 (real-time "where relevant and technically feasible") | in the US, no law requires it; Dexcom's public API is 1–3 h delayed; other clouds publish no API; follower routes change about twice a year per vendor (cloud-layer §1.3) |
| cloud terms of service | contract | Data Act Art. 7(2) voids terms that cut down the user's Data Act rights (EU only) | Dexcom terms forbid bots, scraping and "unauthorized third-party applications"; LibreLinkUp terms prompts stop connectors |
| anti-circumvention | legal | (b)(7) data exemption, renewed since 2015, unopposed so far in this cycle | three-year renewals; no cover for trafficking, commands or contract; Data Act preserves copyright law and forbids abusing technical gaps |
| interface specifications | regulatory / commercial | FDA's modular classifications; many cross-manufacturer combinations | specifications go to contracted companies; no manufacturer publishes a request route; FDA does not require publication |
| regulatory status of a controller | regulatory | iAGC 510(k) path exists and is used (Diabeloop 2025) | requires a manufacturer with a quality system; self-built software has no path to a pump's ACE interface |
| repair | legal | federal (b)(17) exemption | state and EU repair laws exclude medical devices; industry opposes (b)(17) renewal |
| the phone platform | technical / commercial | DMA in the EU (background execution, pairing); Apple's free personal builds | outside the EU these are Apple's voluntary policy; personal builds expire every 7 days |
| selective partnerships | commercial | many bilateral deals | partners are companies; Roche's SmartGuide is moving to exclusive pairing with its own app (**not verified**) |

### 5.2 The maintainer's working view, tested

The view: technology blockers are increasingly being removed, so the picture of success is
increasingly clear regardless of who does it; mechanisms like those that let a person build and run
software on their own Apple device are needed to protect data rights in diabetes.

**Supported:**

- Between **companies**, blockers are coming down quickly. FDA's modular classifications have
  produced cross-maker pump, sensor and algorithm combinations (§2), and the FDA record expects
  interface specifications to be shared by contract.
- In the **EU**, the Data Act creates, for the first time, a legal duty to give a person and their
  chosen third party their device data, in real time where feasible, free to the person, and it
  voids contract terms that cut that right down.
- In the **US**, the §1201 data exemption has been renewed every cycle and drew no opposition in the
  petition phase of this one.

**Not supported, or contradicted:**

- **Device-level protections are increasing, not decreasing.** Each new generation raises the cost
  of independent access. Most authenticated pairing found still uses a secret the person holds, and
  open implementations handle it (Dexcom G7, Libre 3, Tandem; device-layer census). Omnipod 5 is the
  one case found where the app itself is checked (§1.6), and for such a device knowledge of the
  protocol is not enough.
- **The removals run through channels that require being a company with a contract.** Every
  real-time vendor route, every interface specification and every cross-maker integration found is
  bilateral. No manufacturer publishes a route for a non-profit, an individual developer or an
  open-source project beyond Dexcom's delayed, five-user tier. "Regardless of who does it" does not
  hold: today it matters a great deal who does it.
- **The US has no general equivalent of the Data Act.** US rights found are a copyright exemption
  (a defence, not an access duty), HIPAA access against clinics, and state privacy laws without
  format or timing duties.
- **The Data Act gives a right to ask, not a right to build.** It keeps copyright and trade-secret
  protections, lets a manufacturer restrict sharing where security could cause "a serious adverse
  effect on the health, safety or security of natural persons", and forbids getting data by abusing
  technical gaps. For insulin-related devices the health-and-safety carve-out is the one most likely
  to be tested. It also may not reach the glucose value itself if that counts as derived data.
- **The Apple analogy is partial.** A person can build and run software on their own iPhone because
  Apple chooses to allow it (and in the EU because the DMA requires some openness). No law obliges a
  pump or CGM maker to offer the equivalent, and no right-to-repair law reaches medical devices.

**Verdict on the view as first worded:** the view holds for regulated, company-to-company interoperability and for EU data
access. It does not hold for independent access to devices, for control, or for the US: the
blockers that stand in the ecosystem's way specifically (device authentication, issued
credentials, terms of service, bilateral-only routes, three-yearly copyright exemptions) are not
being removed, and some are growing.

**The view as the maintainer clarified it (2026-10-17).** "Regardless of who does it" means that
the requirements are the same for anyone. In the US anyone may meet them who strives to and
fulfils all of them; in practice that means a company is required. A non-profit has no real
advantage in meeting them; what it offers is a layer of oversight, at one level of governance,
over many for-profits, which answers the community's sociological needs. On the technology side,
the cost of the engineering is falling: coding agents are used for increasingly ambitious
projects, device connectivity among them. Tested against the same evidence:

- **Same requirements for anyone: supported.** The FDA classifications in §2 are open to any
  manufacturer that meets the special controls; Tidepool, a non-profit, went through the same 510(k)
  route as a company would (PRECEDENTS). Dexcom offers one "standard, non-negotiable Data Licensing
  Agreement" (§1.2). The Washington act's definitions do not exclude non-profits (§3.6). Apple asks
  healthcare apps to come from "a legal entity that provides the services, and not … an individual
  developer", and its only non-profit concession is a fee waiver for organisations that sell
  nothing ([Apple note](apple-accountability.md) §1.3).
- **A legal entity with contracts is required in practice: supported. "A company" is narrower
  than the evidence.** Every real-time route and interface specification found is a contract
  between legal entities (above); none is open to an individual or an unincorporated project.
  Tidepool, a non-profit, took the same 510(k) route a company would (PRECEDENTS), so what is
  required is an entity with a quality system and contracts. In practice that is usually a
  company.
- **The non-profit's role is oversight, not an advantage in meeting requirements: consistent with
  the precedents.** CNCF certifies vendors' offerings against one upstream with the same public
  tests, and the Open Home Foundation binds its commercial partners by contract to contribute a
  majority of their profit from licensed products; neither carries those companies' own regulatory
  duties (PRECEDENTS). Whether a manufacturer
  values such a layer is not shown by any source read.
- **Falling engineering cost: plausible, not measured here.** No source read measures the effect of
  coding agents on device-integration work. It also bears on a different blocker from the ones that
  are growing: agents lower the cost of building an integration, while device authentication, app
  attestation and issued credentials (§1.6) decide who is authorised to use one. Those are met by
  the entity and its agreements, not by engineering.

Read this way, the evidence supports the view: the engineering is becoming cheaper for everyone,
the requirements are the same for everyone, and what stands between the ecosystem and the devices
is being an entity that meets them. That is the structure the
[proposed ecosystem drawing](../../00-overview/perspective/STRUCTURES.md) (1·proposed, 2·agreement, 2·controller-operator) shows.

### 5.3 What an organisation would need to use each right

| right or route | what the organisation would have to be or have |
|---|---|
| Data Act third party (EU) | a user-authorisation flow by which the person asks the data holder to send data to it; a GDPR legal basis for health data (likely explicit consent) and probably an EU representative if not established in the EU; written purposes, erasure and no-onward-sharing rules matching Art. 6; trade-secret confidentiality measures on request; acceptance that it may not build a "competing connected product"; capacity to complain to a national authority or go to a certified dispute body when refused; willingness to pay cost-based compensation (whether a US 501(c)(3) counts as an SME or a "not-for-profit research organisation" under Art. 9(4) is for counsel) |
| Data Act user access via a self-hosted tool | nothing institutional: the person requests their own data. An organisation could publish request templates and track refusals as evidence |
| DMCA (b)(7), "on behalf of a patient" | acting only for named patients, for data access only; no distribution of circumvention tools (anti-trafficking); separate compliance with CFAA and terms; evidence for each renewal cycle |
| Dexcom developer API | a registered developer; for more than five users, a commercial partnership, the non-negotiable Data Licensing Agreement and Dexcom's review; the 1–3 h delay |
| FDA-regulated interoperability (ACE/iAGC) | to be a "connected device company" in a manufacturer's contract: a manufacturer's quality system, complaint and adverse-event handling allocated by contract (§2), and in practice a cleared product |
| HIPAA access through clinics | the person's request to their clinic; the organisation as a recipient the person designates (the precise rule for designating a third party is **not verified** here) |
| Washington My Health My Data Act | as a recipient of Washington residents' data: consent, a consumer health data privacy policy, access and deletion handling |
| FTC Health Breach Notification Rule | as a probable PHR vendor or related entity: breach detection and notice to people, the FTC and media |

## 6. Gaps

- Contract texts not public or not read: Dexcom's Data Licensing Agreement; Abbott, MiniMed, Tandem
  and Insulet consumer terms; Tidepool's API terms; Roche's partner onboarding.
- The FDA 2019 iAGC announcement page returned 404; Insulet's Omnipod 5 decision summary was not
  read.
- MiniMed's 8-K, Medtronic's iAGC release, the Glooko–Roche release, Roche's exclusive-pairing
  report, HTI-5 status, UK commencement and the digital-omnibus status were read through search
  summaries only.
- Abbott's and Dexcom's own pages describe no fees; whether any exist is unknown.
- No state right-to-repair statute other than Minnesota's was read.
- The CMS diabetes page lists pledges, not delivered connections.

## 7. Points for a reviewer to verify

1. **Data Act scope for CGM data:** whether a glucose value computed by the manufacturer's algorithm
   is "pre-processed" (in scope) or "inferred or derived" (Recital 15, out of scope), and whether a
   pump's delivery record is product data or related-service data.
2. **Data Act Art. 4(2):** whether CGM and pump data sharing could be restricted under the
   health-and-safety security carve-out, and which "security requirements ... laid down by Union or
   national law" (for example the Medical Device Regulation) a manufacturer could cite.
3. **Data Act "third party":** whether a US non-profit can be a third party and data recipient;
   whether it qualifies for cost-only compensation under Art. 9(4); whether an EU representative is
   required; and whether an AID app could be a "product that competes with the connected product"
   under Art. 6(2)(e).
4. **Data Act Art. 4(11) and 5(5):** what "abuse gaps in the technical infrastructure" means for
   follower-service connectors used with the person's own credentials.
5. **Digital omnibus:** current status of the Data Act amendments (procedure 2025/0360(COD)).
6. **37 CFR 201.40(b)(7):** whether "on behalf of a patient" covers an organisation running a hosted
   service for many patients, and how the anti-trafficking rule applies to publishing source code.
7. **10th triennial rulemaking:** whether any late filing opposes (b)(7); when the proposed rule is
   due.
8. **FDA:** whether the "plans" in the ACE and iAGC decision summaries create any obligation to deal
   with a qualified third party, or only to have a process; whether any FDA statement since 2019
   addresses non-manufacturer software.
9. **Information blocking:** whether HTI-5 has been finalised and whether it changes actor
   definitions.
10. **HIPAA:** the current rule for an individual directing a copy of their records to a third party
    (45 CFR 164.524), after the 2020 court decision that limited parts of it.
11. **Washington act:** whether the foundation or a hosted service would be a "regulated entity",
    and what other state laws (Nevada, Connecticut, New York) add.
12. **Right to repair:** the medical-device exclusions in the New York, Oregon, California and
    Colorado statutes, and the status of the Vermont and Rhode Island bills.
13. **Dexcom terms §5.11:** how the bans on automated access and "unauthorized third-party
    applications" interact with the DMCA (b)(7) exemption and, in the EU, with Data Act Art. 7(2).
14. **§524B as the driver of device changes:** whether FD&C Act §524B and FDA's premarket
    cybersecurity guidance expect a manufacturer to show that a device's interfaces authenticate and
    authorise those that connect. If they do, that explains why device-level controls tighten and
    do not loosen, independent of whether §524B reaches a DIY build.
15. **Omnipod 5 credential:** who issues the credential behind the community driver's certificate
    store and App Attest service, and whether that driver runs against a real pod. Read at mechanism
    level only, under the device-layer census's disclosure rule; §1.6 is read from file names.

## Sources

All read 2026-10-17 unless noted.

- Dexcom: <https://developer.dexcom.com/docs/dexcomv3/endpoint-overview/> ;
  <https://developer.dexcom.com/docs/dexcom/scopes-access/> ;
  <https://developer.dexcom.com/docs/dexcom/getting-started/> ;
  <https://developer.dexcom.com/docs/dexcom/sandbox-data/> ;
  <https://www.dexcom.com/partnerships/integrations-and-compatibility> ;
  <https://www.dexcom.com/en-us/legal/terms-of-use> ;
  <https://www.biospace.com/fda-clears-dexcom-real-time-apis-for-third-party-apps-and-devices>
- Abbott: <https://www.diabetescare.abbott/partnerships/integrations/en.html> ;
  <https://docs.junction.com/wearables/guides/abbott-libreview>
- MiniMed: <https://www.minimed.com/en-us/support/product-support/minimed-flex/sharing-your-data> ;
  SEC 8-K exhibit (search summary); Medtronic release 2025-09-02 (search summary)
- Tandem: <https://www.tandemdiabetes.com/support-center/pumps-and-supplies/cartridges/article/data-sharing-capability-tandem-source>
- Insulet: <https://www.omnipod.com/innovation>
- Roche: <https://simplifier.net/guide/RDCEMRImplementationGuide/sandboxapi>
- Ypsomed, Sequel, Diabeloop, Medtrum: links in §1.7
- Tidepool: <https://www.tidepool.org/> ; <https://tidepool.org/loop-device-partners> ;
  <https://www.tidepool.org/blog/the-inside-scoop-on-third-party-control-for-ace-pumps>
- CMS: <https://www.cms.gov/health-tech-ecosystem/early-adopters/diabetes-obesity> ;
  <https://www.cms.gov/newsroom/press-releases/white-house-tech-leaders-commit-create-patient-centric-healthcare-ecosystem>
- FDA: <https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN180058.pdf> ;
  <https://www.accessdata.fda.gov/cdrh_docs/reviews/DEN190034.pdf>
- EU: <http://publications.europa.eu/resource/celex/32023R2854> ;
  <http://publications.europa.eu/resource/celex/32025R0327> ;
  <http://publications.europa.eu/resource/celex/32024L1799> ;
  <https://digital-strategy.ec.europa.eu/en/library/commission-publishes-frequently-asked-questions-about-data-act> ;
  <https://digital-markets-act.ec.europa.eu/developer-portal/interoperability/apple-specification-proceedings-interoperability-connected-devices-and-request-based-process_en>
- US copyright: <https://www.ecfr.gov/current/title-37/chapter-II/subchapter-A/part-201/section-201.40> ;
  <https://www.copyright.gov/1201/2027/> ; <https://www.copyright.gov/1201/2027/petitions/renewal/>
- FTC: <https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-318> ;
  <https://www.ftc.gov/legal-library/browse/rules/health-breach-notification-rule>
- States: <https://app.leg.wa.gov/RCW/default.aspx?cite=19.373&full=true> ;
  <https://www.revisor.mn.gov/statutes/cite/325E.72>
