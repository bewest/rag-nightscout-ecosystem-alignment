# Digital Rights and Legal Protections for Open-Source Diabetes Software

**Status:** Living Document  
**Last Updated:** October 2026  
**Purpose:** Document the legal frameworks relevant to open-source diabetes software development, distribution, and use

**Updated 2026-10-17:** brought up to date the current wording of the medical device data exemption (37 CFR 201.40(b)(7)), the dates and filings of the 2027 rulemaking, the phone exemption (b)(9), the EU Data Act (new section under [Data Portability Rights](#data-portability-rights)) and the right-to-repair landscape. Each was re-read in the primary source on 2026-10-17; the research behind it is in [Vendor programmes and data rights](60-research/structures-2026-10-17/vendor-programs-and-data-rights.md) §3–§4, which also lists the points for counsel to check (§7).

---

> **IMPORTANT: THIS DOCUMENT IS NOT LEGAL ADVICE**
> 
> This document provides general information about legal frameworks that may be relevant to open-source diabetes software. It is NOT legal advice, and the authors are NOT attorneys. The legal landscape varies significantly by jurisdiction, is subject to change, and involves unsettled questions. **Consult qualified legal counsel before relying on any information here for specific situations.**

---

## Table of Contents

1. [Overview](#overview)
2. [Open Source Licensing Protection (GPL v3)](#open-source-licensing-protection-gpl-v3)
3. [DMCA Section 1201 Medical Device Exemption](#dmca-section-1201-medical-device-exemption)
4. [Interoperability Defense](#interoperability-defense)
5. [Negotiated Access: Agreements with Manufacturers](#negotiated-access-agreements-with-manufacturers)
6. [Right to Repair Landscape](#right-to-repair-landscape)
7. [Responding to Improper DMCA Takedown Requests](#responding-to-improper-dmca-takedown-requests)
8. [Best Practices for Projects](#best-practices-for-projects)
9. [Resources and References](#resources-and-references)

---

## Overview

The open-source diabetes technology community (#WeAreNotWaiting) operates within a complex legal landscape. This document explains the legal frameworks that protect developers, contributors, and users of open-source diabetes software—and their limitations.

**Key Protections:**
- GPL v3 licensing provides warranty disclaimers and liability limitations
- DMCA Section 1201 exemptions permit patients, and those acting for them, to access data from their own medical devices, and permit medical device repair
- Interoperability rights support data access and portability
- In the EU, the Data Act (applying since September 2025) gives users of connected products a right to their data and to have it shared with a third party they choose, within limits (see [EU Data Act](#eu-data-act-regulation-eu-20232854))
- Right-to-repair laws are expanding access to device repair
- Written agreements with manufacturers can secure access that does not depend on any exemption

**Key Limitations:**
- "Jailbreaking" devices for DIY looping remains in a legal gray area
- Every exemption expires at the end of its three-year cycle unless renewed (the current cycle ends October 28, 2027)
- Modifying therapeutic device behavior is not covered by current exemptions
- Distributing circumvention tools may trigger anti-trafficking provisions

The goal of this document is to help the community understand these protections and operate within defensible legal boundaries.

---

## Open Source Licensing Protection (GPL v3)

Most DIY diabetes projects use the **GNU General Public License version 3 (GPL v3)**, which provides significant legal protections for developers.

### Warranty Disclaimer (Section 15)

The GPL v3 explicitly disclaims all warranties:

> "THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW. EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM 'AS IS' WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. **THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM IS WITH YOU.** SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION."

### Limitation of Liability (Section 16)

The GPL v3 limits developer liability:

> "IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE USE OR INABILITY TO USE THE PROGRAM..."

### Anti-Tivoization (Section 3)

GPL v3 includes provisions (sometimes called "anti-tivoization") that apply in a **narrow context**: when a distributor conveys GPLv3-covered software as part of a "User Product" (consumer device). In that case, the distributor must provide the installation information necessary to install and execute modified versions.

**Limitations:**
- This only applies when someone *distributes* GPL v3 software in a consumer product
- It does not create a general "right to modify" devices you already own
- Medical devices distributed by manufacturers typically don't include GPL v3 software
- This provision is not a substitute for right-to-repair laws or DMCA exemptions

### Copyleft Protection

Any derivative works must also be released under GPL v3, preventing proprietary forks and ensuring the community retains access to improvements.

### How These Provisions May Apply

For diabetes software projects, GPL v3 may provide:

1. **Contractual disclaimers** that shift risk to users—however, enforceability varies by jurisdiction and may not apply to gross negligence, willful misconduct, or product liability claims in some countries (especially for medical-related software)
2. **Clear communication** that users accept responsibility for evaluating the software
3. **Copyleft requirements** that derivative works remain open under the same license

**Important caveats:**
- GPL disclaimers are contractual terms, not absolute immunity from liability
- Some jurisdictions (notably parts of the EU) limit how much liability can be disclaimed for consumer products or health-related software
- Product liability laws may apply regardless of license disclaimers
- The legal treatment of open-source medical software remains largely untested in courts

### Recommended License Notices

Include at the top of source files:

```
/*
 * This file is part of [Project Name].
 * 
 * [Project Name] is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 * 
 * [Project Name] is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with [Project Name]. If not, see <https://www.gnu.org/licenses/>.
 */
```

---

## DMCA Section 1201 Medical Device Exemption

The Digital Millennium Copyright Act (DMCA) Section 1201 prohibits circumventing technological protection measures (TPMs) that control access to copyrighted works. However, the Librarian of Congress grants exemptions through a triennial rulemaking process.

### Current Exemptions (October 2024 – October 2027)

The **9th Triennial DMCA 1201 Rulemaking** concluded in October 2024. The final rule was published on **October 25, 2024**, with exemptions effective **October 28, 2024** through **October 28, 2027**. The exemptions are codified at 37 CFR 201.40.

#### Medical Device Data Exemption

This is the exemption most directly about diabetes data. First granted in 2015 and since renewed, it is codified at 37 CFR 201.40(b)(7). The current text reads:

> "Literary works consisting of compilations of data generated by medical devices or by their personal corresponding monitoring systems, where such circumvention is undertaken by or on behalf of a patient for the sole purpose of lawfully accessing data generated by a patient's own medical device or monitoring system. Eligibility for this exemption is not a safe harbor from, or defense to, liability under other applicable laws, including without limitation the Health Insurance Portability and Accountability Act of 1996, the Computer Fraud and Abuse Act of 1986, or regulations of the Food and Drug Administration."

(Read from the eCFR, title 37 up to date as of 2026-10-15, on 2026-10-17.) The 2015 version was limited to implanted devices and to passive monitoring of wireless transmissions. Neither limit is in the current text. Whether "on behalf of a patient" covers an organisation that runs a hosted service for many patients is a question for counsel.

**What it supports:** reading your own CGM and pump data, and having a tool or helper you choose read it for you.

**What it does not do:** it is not a safe harbor from other laws. The regulation itself names HIPAA, the Computer Fraud and Abuse Act and FDA regulations as unaffected. It does not cover sending commands to a device, modifying device software, or breaching terms of service.

#### The Next Rulemaking (2027)

The Copyright Office's **10th triennial rulemaking** decides which exemptions continue after October 28, 2027. Renewal petitions have been filed in it, including one for the medical device data exemption by the Coalition of Medical Device Patients and Researchers ([petition](https://www.copyright.gov/1201/2027/petitions/renewal/Renewal-Pet-Medical-Device-Data-Coalition-of-Medical-Device-Patients-and-Researchers.pdf)). Renewal is not automatic: an exemption that meets opposition with evidence can be narrowed or lost. Dated, counted cases where people lost access to their own device data are the kind of evidence that supports renewal (see [Negotiated Access](#negotiated-access-agreements-with-manufacturers)).

**Schedule and filings so far** (from the Copyright Office's [2027 rulemaking page](https://www.copyright.gov/1201/2027/) and [renewal petitions page](https://www.copyright.gov/1201/2027/petitions/renewal/), read 2026-10-17):

| step | date |
|---|---|
| Notice of inquiry and request for petitions | 2026-06-09 |
| Petitions to renew current exemptions, and for new ones, due | 2026-08-24 |
| Comments on renewal petitions due | 2026-09-28 |
| Proposed rule | not yet posted on 2026-10-17 |

- **Medical device data (b)(7):** one renewal petition (the Coalition above). No filing on the renewal page opposes it.
- **Medical device repair (b)(17):** several renewal petitions, from independent servicers and iFixit. The Advanced Medical Technology Association (AdvaMed, the medical-technology trade association) and Philips North America filed oppositions; each asks the Office not to renew the repair exemption through the streamlined procedure. AdvaMed also opposes one petition's proposed expansion. The Joint Creators (games, film and music trade bodies) say they do not oppose renewal of the existing exemption, but oppose that expansion.
- **Phone jailbreaking (b)(9):** the Electronic Frontier Foundation petitioned to renew it; no opposition is listed.

The page lists all the oppositions under one heading, "Medical Devices"; that they address (b)(17) and not (b)(7) was read from the filings themselves. Late filings and the proposed rule may change this picture; check [copyright.gov/1201/2027](https://www.copyright.gov/1201/2027/) for the current state.

#### Medical Device Repair Exemption

**What is permitted:**
- Circumvention of TPMs on medical devices **solely for diagnosis, maintenance, or repair** purposes
- Covers insulin pumps, CGMs, and other diabetes management hardware
- Third-party repair services can legally bypass firmware locks
- Patients can seek third-party repair without DMCA liability

**What is NOT covered by the repair exemption:**
- Device **modification** beyond repair (e.g., altering therapeutic behavior)
- **Unlocking features** disabled by manufacturers
- **"Jailbreaking"** to enable third-party integrations (e.g., DIY closed-loop systems)

**Note:** The 2024 rulemaking also includes **separate exemptions** for:
- **Security research** (good-faith security testing of devices, subject to conditions)
- **Computer program interoperability** (circumvention to achieve interoperability of independently created programs)
- **Phone jailbreaking** (37 CFR 201.40(b)(9)): circumvention on smartphones and "portable all-purpose mobile computing devices" to run lawfully obtained apps, "for the sole purpose of enabling interoperability of such applications with computer programs on the smartphone or device, or to permit removal of software". It covers the phone, not the medical device. It is in the current (2024) rule and has been petitioned for renewal in the 2027 rulemaking.

These other exemptions *may* be relevant to some DIY diabetes activities, but their applicability is fact-specific and legally uncertain. The security research exemption, for example, requires "good faith" research and has various conditions. Consult legal counsel before relying on any exemption.

#### FDA Position

The FDA submitted a support letter for the 2024 exemption stating:

> "The FDA does not share the view that an exemption from liability under 17 U.S.C. §1201 for circumvention conducted solely for the purpose of diagnosis, maintenance, or repair of medical devices would necessarily and materially jeopardize the safety and effectiveness of medical devices."

The FDA explicitly noted it does **not** support exemptions for modification beyond repair.

### Devices Covered

| Device Type | Examples | Covered Activities |
|-------------|----------|-------------------|
| Insulin Pumps | Omnipod, Medtronic MiniMed, Tandem t:slim | Repair, diagnostics, servicing |
| CGMs | Dexcom G6/G7, FreeStyle Libre, Guardian | Repair, sensor troubleshooting |
| AID Systems | Control-IQ, Basal-IQ integrated systems | Servicing pump+CGM components |

### Implications for DIY Looping

Reading data from your own devices is supported by the medical device data exemption above. The exemptions do **not** provide a safe harbor for the rest of what DIY automated insulin delivery (AID) systems like Loop, OpenAPS, or AndroidAPS do. Those activities involve:

- Enabling unauthorized communications between devices
- Modifying therapeutic behavior
- Using devices in ways not intended by manufacturers

This means DIY looping remains in a **legal gray area** under DMCA 1201. The community operates based on:

1. Open-source licensing protections (GPL v3)
2. Interoperability defenses
3. The practical reality that manufacturers have generally not pursued enforcement

### Anti-Trafficking Provisions

Note that Section 1201(a)(2) prohibits **trafficking** in circumvention tools—even if the circumvention itself is permitted. This means:

- Distributing pre-patched binaries may be legally risky
- Sharing source code and instructions is generally safer
- Users building their own systems from source reinforces informed consent

---

## Interoperability Defense

Several legal frameworks support the right to access and use personal health data.

### EU Software Directive (2009/24/EC)

Article 6 of the EU Software Directive permits reverse engineering for **interoperability purposes**:

> "The authorization of the rightholder shall not be required where reproduction of the code and translation of its form... are indispensable to obtain the information necessary to achieve the interoperability of an independently created computer program with other programs..."

This provides a defense for:
- Analyzing device communication protocols
- Creating software that interoperates with commercial devices
- Enabling data portability between systems

### Data Portability Rights

Under various regulations (GDPR in EU, state privacy laws in US), individuals have rights to access their personal data. For diabetes management:

- CGM readings are personal health data
- Users generally have rights to request copies of their data from data controllers
- Manufacturers may be obligated to provide data export mechanisms

**Important distinction:** Data access rights under GDPR and similar laws are separate from rights to circumvent technological protection measures. Having a right to your CGM data does NOT automatically authorize:
- Bypassing manufacturer firmware locks to extract data
- Violating terms of service or end-user license agreements
- Circumventing TPMs that protect copyrighted software

These are distinct legal questions governed by different bodies of law. In the United States, the DMCA's [medical device data exemption](#medical-device-data-exemption) does permit circumvention for a patient to access their own device data, but it does not override terms of service or other laws.

#### EU Data Act (Regulation (EU) 2023/2854)

> **Draft for legal review.** This section is a non-lawyer's reading of the Regulation, for review by counsel before anyone relies on it. The open questions are listed in the [vendor note §7](60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#7-points-for-a-reviewer-to-verify).

The Data Act has applied since **12 September 2025** (Art. 50). It gives the user of a "connected product" (a device that collects data about its use and can communicate it) rights against the "data holder" (the company that holds the product's data, often the manufacturer running the cloud). Its recitals name "medical and health devices" among connected products (Recital 14). Its obligation to design products so that users can reach the data directly applies to products placed on the market after 12 September 2026 (Art. 3(1), Art. 50).

**What it gives the person (in the EU):**

- **Access to their own data (Art. 4(1)).** Where the user cannot reach the data directly from the product, the data holder must make "readily available data" accessible "without undue delay, of the same quality as is available to the data holder, easily, securely, free of charge, in a comprehensive, structured, commonly used and machine-readable format and, where relevant and technically feasible, continuously and in real-time".
- **Sharing with a third party the person chooses (Art. 5(1)).** "Upon request by a user, or by a party acting on behalf of a user", the data holder must make the same data available to a third party, on the same terms, "free of charge to the user". The data holder may ask the third party for reasonable compensation; for a small or medium-sized enterprise or a not-for-profit research organisation, that may not exceed cost (Art. 9(4)).
- **Contracts cannot take these rights away.** A contract term that excludes or varies the user's rights in this chapter is "not binding on the user" (Art. 7(2)).

**What the third party must accept (Art. 6):** use the data only "for the purposes and under the conditions agreed with the user"; erase it when no longer needed; no profiling unless needed for the service; no passing it on except by contract with the user; not use it to develop a product that competes with the connected product it came from. Companies designated as gatekeepers under the Digital Markets Act may not be the third party (Art. 5(3)).

**Its limits:**

- **Health and safety.** The user and data holder may contractually restrict access or sharing "if such processing could undermine security requirements of the connected product, as laid down by Union or national law, resulting in a serious adverse effect on the health, safety or security of natural persons". A data holder that refuses on this ground must notify the national competent authority (Art. 4(2)).
- **Trade secrets.** Trade secrets are disclosed only under agreed confidentiality measures; "in exceptional circumstances" a data holder that shows serious economic damage is "highly likely" may refuse a specific request, case by case (Art. 4(6)–(8); for third parties, Art. 5(9)–(11)).
- **No abusing technical gaps.** The user and the third party "shall not use coercive means or abuse gaps in the technical infrastructure of a data holder which is designed to protect the data in order to obtain access to data" (Art. 4(11), 5(5)). The Act is also without prejudice to intellectual-property law, including the EU copyright rules that protect technological measures (Art. 1(8)). It is a right to **ask** for the data, with a complaint route to a national authority, not a licence to reverse-engineer.
- **Derived data excluded.** Information "inferred or derived" from the data, "in particular by means of proprietary, complex algorithms", is outside its scope (Recital 15). Whether a CGM glucose value, which the manufacturer's algorithm computes from the raw sensor signal, counts as in-scope data or as derived data is not settled, and is the most consequential open question for diabetes devices.
- **Small manufacturers.** These obligations do not apply to data from products made by micro and small enterprises that are not linked to larger ones (Art. 7(1)).
- **Geography.** It concerns connected products and services in the EU. It creates no right in the United States.

[![The person designates who receives their data: under the EU Data Act the person may access their data and designate a third party; the manufacturer must share at the person's request, real-time where feasible; the third party may use it only for the agreed purposes](00-overview/perspective/diagrams/idea-designated-third-party.svg)](00-overview/perspective/STRUCTURES.md#ideadesignated-third-party)

*The drawing is from the [structures gallery](00-overview/perspective/STRUCTURES.md#ideadesignated-third-party).*

Text read on EUR-Lex (<https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2854>) on 2026-10-17.

### Fair Use and Research

In the United States, fair use (17 U.S.C. § 107) may protect certain activities:

- Security research on medical devices
- Educational analysis of device protocols
- Commentary and criticism of device limitations

### The Abbott Labs Precedent (2019)

In 2019, Abbott Laboratories sent a DMCA takedown notice to remove a GitHub project (Libre2-patched-App) that modified their LibreLink app. This highlighted:

1. **Manufacturers will use copyright claims** to restrict third-party access
2. **Hosting platforms comply** with takedown requests (safe harbor)
3. **Counter-notice procedures exist** but require legal risk tolerance

The community response included:
- Moving development to jurisdictions with stronger interoperability protections
- Focusing on original code rather than modified proprietary binaries
- Documenting interoperability defenses

---

## Negotiated Access: Agreements with Manufacturers

The protections above are defences: they describe what people and projects may do without the manufacturer's permission. Some newer devices accept commands, and sometimes data requests, only from a client holding a credential the manufacturer issues. For those devices, understanding the protocol is not enough, and access depends on an agreement with the manufacturer.

An agreement can secure the same rights the [Data Rights Primer](10-domain/data-rights-primer.md) describes (access, export, share, delegate, audit) without depending on an exemption that expires every three years. What such an agreement needs, from both sides, is proposed in [Ready to agree with a device manufacturer](00-overview/PARTNER-READINESS.md):

- **Start with read-only access.** Observing and exporting data is a separate, lower-risk agreement from configuring a device or controlling insulin delivery, and does not have to wait for them.
- **Write the rights into the terms.** Nonexclusive access for any qualifying implementation; access the patient directs and can move; notice before changes that break an integration; revocation only by a published process; freedom to publish interoperability results.
- **Settle licensing early.** A protocol specification shared under a non-disclosure agreement may not be implementable in source code published under the GPL or AGPL; this has to be resolved in the agreement.
- **Keep records.** A shared complaint and incident intake gives a manufacturer a channel it needs, and gives advocacy its evidence: dated, counted cases where a device, app or cloud change cut people off from their own data.

Agreements add to the rights above; they do not replace them.

---

## Right to Repair Landscape

Right-to-repair laws are expanding across the United States and internationally.

### US State-Level Laws

As of January 2026, multiple states have enacted or are considering right-to-repair legislation. The landscape is evolving rapidly.

**General observations:**
- Most enacted laws focus on **consumer electronics** and **agricultural equipment**
- **Medical devices are frequently exempted** from these laws, either explicitly or through definitions that exclude FDA-regulated devices
- Coverage, effective dates, and enforcement mechanisms vary significantly by state

**For current information:**
- Repair.org (The Repair Association): https://www.repair.org/legislation
- iFixit Right to Repair Tracker: https://www.ifixit.com/Right-to-Repair
- State legislature websites for specific bill text and status

**Note:** This document does not attempt to maintain a current table of state laws due to the rapidly changing landscape. Always verify current law in your jurisdiction.

**Medical-device exclusions confirmed in the text (read 2026-10-17; draft for legal review):**

- **Minnesota** ([Minn. Stat. 325E.72](https://www.revisor.mn.gov/statutes/cite/325E.72)): "Nothing in this section applies to manufacturers or distributors of a medical device as defined in the Federal Food, Drug, and Cosmetic Act", nor to digital products or software made for use in a medical setting.
- **European Union** ([Directive (EU) 2024/1799](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024L1799)): the repair obligation reaches only the goods listed in its Annex II (household washing machines, dishwashers, refrigerators, displays, welding equipment, vacuum cleaners, servers and data storage, phones and tablets, tumble dryers, and goods with light-transport batteries). Medical devices are not listed.
- Other states' statutes (for example New York, Oregon, California and Colorado) are described by trade and advocacy sources as excluding medical devices; their texts have not been read here.

Where checked, then, repair laws do not reach diabetes devices. The only repair route for them found so far is the federal §1201 [medical device repair exemption](#medical-device-repair-exemption), and the medical-technology industry is opposing its renewal in the [2027 rulemaking](#the-next-rulemaking-2027).

### Federal Efforts

- **FTC Right to Repair Policy Statement (2021):** Signaled increased enforcement against repair restrictions
- **Executive Order on Competition (2021):** Directed agencies to address right-to-repair barriers
- **Proposed federal legislation:** Various bills addressing medical device repair access

### Relevance to Diabetes Devices

Right-to-repair laws primarily address:
- Access to parts and repair manuals
- Diagnostic software access
- Repair service authorization

They do **not** directly address:
- Software modification for interoperability
- DIY closed-loop systems
- Circumvention of TPMs (covered by DMCA exemptions)

However, the movement creates a favorable political and legal environment for:
- Challenging manufacturer restrictions
- Advocating for expanded exemptions
- Building public support for device access rights

---

## Responding to Improper DMCA Takedown Requests

If your project receives a DMCA takedown notice, here's how to evaluate and respond.

### Evaluating the Notice

Ask these questions:

1. **Is there actual copyrighted material?**
   - Original code you wrote is not infringing
   - Protocols and data formats are generally not copyrightable
   - Only actual copying of copyrighted code triggers liability

2. **Does an exemption apply?**
   - Repair exemption (2024-2027) for diagnosis, maintenance, repair
   - Interoperability exception under EU law (if applicable)
   - Fair use for research, education, commentary

3. **Is this a misuse of DMCA?**
   - DMCA is for copyright, not patents or trade secrets
   - Threatening legal action you don't intend to pursue is abuse
   - False claims can result in liability for the sender

### Counter-Notice Procedure

If you believe the takedown was improper, you can file a counter-notice:

1. **Identify the removed material** and its former location
2. **State under penalty of perjury** that you have a good-faith belief the material was removed by mistake or misidentification
3. **Consent to jurisdiction** of federal court in your district
4. **Provide contact information** and signature

**Important:** Filing a counter-notice exposes you to potential lawsuit. The claimant has 10-14 business days to file suit, or the material must be restored.

### Practical Considerations

**Before receiving a notice:**
- Keep original code separate from any proprietary elements
- Document your development process and sources
- Use established open-source licenses consistently
- Consider hosting in jurisdictions with stronger protections

**If you receive a notice:**
- Don't panic—evaluate the claims carefully
- Consult with an attorney if possible (EFF, Software Freedom Law Center)
- Consider whether to comply, counter-notice, or negotiate
- Document everything for potential future defense

### Resources for Legal Help

- **Electronic Frontier Foundation (EFF):** eff.org
- **Software Freedom Law Center:** softwarefreedom.org
- **Software Freedom Conservancy:** sfconservancy.org
- **GitHub Legal Resources:** docs.github.com/en/site-policy/dmca-takedown-policy

---

## Best Practices for Projects

### Licensing

1. **Use GPL v3** for strong copyleft protection and built-in disclaimers
2. **Include license headers** in every source file
3. **Maintain a clear LICENSE file** in the repository root
4. **Track contributions** with a Contributors file or DCO sign-off

### Disclaimers

Include explicit disclaimers in README and documentation:

```
IMPORTANT SAFETY NOTICE

This software is provided for informational and research purposes only. 
It is NOT a medical device and has NOT been approved by any regulatory 
body (FDA, CE, etc.) for medical use.

DO NOT rely on this software for medical decisions. Always consult 
qualified healthcare professionals for diabetes management.

THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THIS SOFTWARE 
IS WITH YOU. The developers assume no liability for any damages arising 
from its use.
```

### Code Hygiene

1. **Don't include proprietary code** from manufacturer apps or firmware
2. **Document protocol research** as original work with interoperability purpose
3. **Distribute source code only**—let users build their own binaries
4. **Keep circumvention tools separate** from main project code

### Documentation

1. **Explain the purpose** clearly (data access, interoperability, personal use)
2. **Cite legal frameworks** that support the project's legitimacy
3. **Provide informed consent warnings** before installation
4. **Link to official resources** for regulatory and legal information

---

## Resources and References

### Legal Frameworks

**DMCA Section 1201:**
- US Copyright Office 1201 Proceedings: https://www.copyright.gov/1201/
- 2024 Final Rule: https://www.federalregister.gov/documents/2024/10/28/2024-24563/
- 17 U.S.C. § 1201: https://www.law.cornell.edu/uscode/text/17/1201
- 37 CFR 201.40 (current exemptions, eCFR): https://www.ecfr.gov/current/title-37/chapter-II/subchapter-A/part-201/section-201.40
- 2027 (10th triennial) rulemaking: https://www.copyright.gov/1201/2027/

**EU Data Act:**
- Regulation (EU) 2023/2854: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2854
- Commission FAQ: https://digital-strategy.ec.europa.eu/en/library/commission-publishes-frequently-asked-questions-about-data-act

**GPL v3:**
- Full License Text: https://www.gnu.org/licenses/gpl-3.0.html
- How to Apply: https://www.gnu.org/licenses/gpl-howto.html
- FAQ: https://www.gnu.org/licenses/gpl-faq.html

**EU Software Directive:**
- Directive 2009/24/EC: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024

### Academic Research

- Birmingham Law School (2022): "DIY Artificial Pancreas Systems and the Challenges for the Law" - https://onlinelibrary.wiley.com/doi/10.1111/dme.14897
- Nature Digital Medicine (2019): "Open source automated insulin delivery: addressing the challenge" - https://www.nature.com/articles/s41746-019-0202-1

### Community Resources

- OpenAPS Documentation: https://openaps.readthedocs.io
- Nightscout Project: https://nightscout.github.io
- Open Source Diabetes: https://www.opensourcediabetes.org
- We Are Not Waiting: https://www.wearenotwaiting.com

### Legal Support Organizations

- Electronic Frontier Foundation: https://www.eff.org
- Software Freedom Law Center: https://softwarefreedom.org
- Software Freedom Conservancy: https://sfconservancy.org
- GitHub DMCA Policy: https://docs.github.com/en/site-policy/dmca-takedown-policy

### Position Statements

Various diabetes organizations have published position statements on DIY technology:
- Diabetes UK
- Diabetes Australia  
- JDRF (Breakthrough T1D)

These generally acknowledge clinical benefits while noting the lack of formal regulatory framework.

---

## Related Documents

- [Data Rights Primer](10-domain/data-rights-primer.md) - Plain-language guide to the Five Fundamental Diabetes Data Rights (Access, Export, Share, Delegate, Audit)
- [Progressive Enhancement Framework](10-domain/progressive-enhancement-framework.md) - 10-layer capability model for diabetes technology
- [Ready to agree with a device manufacturer](00-overview/PARTNER-READINESS.md) - Draft proposal: access tiers, agreement terms, complaint and incident handling

---

## Document History

| Date | Change |
|------|--------|
| January 2026 | Initial document created |
| January 2026 | Added cross-reference to Data Rights Primer |
| October 2026 | Added the medical device data exemption, the 2027 rulemaking, and negotiated access |
| 2026-10-17 | Current (b)(7) text; 2027 rulemaking dates and filings; (b)(9); EU Data Act; right-to-repair exclusions confirmed. Source: [vendor programmes and data rights](60-research/structures-2026-10-17/vendor-programs-and-data-rights.md) |

---

## Disclaimer

This document is for informational purposes only and does not constitute legal advice. The legal landscape is complex and evolving. Consult with qualified legal counsel for specific situations.

The authors of this document are not attorneys and make no representations about the accuracy or completeness of this information. Use at your own risk.
