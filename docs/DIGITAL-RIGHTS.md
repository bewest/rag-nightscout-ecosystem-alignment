# Digital Rights and Legal Protections for Open-Source Diabetes Software

**Status:** Living Document  
**Last Updated:** January 2026  
**Purpose:** Document the legal frameworks relevant to open-source diabetes software development, distribution, and use

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
5. [Right to Repair Landscape](#right-to-repair-landscape)
6. [Responding to Improper DMCA Takedown Requests](#responding-to-improper-dmca-takedown-requests)
7. [Best Practices for Projects](#best-practices-for-projects)
8. [Resources and References](#resources-and-references)

---

## Overview

The open-source diabetes technology community (#WeAreNotWaiting) operates within a complex legal landscape. This document explains the legal frameworks that protect developers, contributors, and users of open-source diabetes software—and their limitations.

**Key Protections:**
- GPL v3 licensing provides warranty disclaimers and liability limitations
- DMCA Section 1201 exemptions permit medical device repair activities
- Interoperability rights support data access and portability
- Right-to-repair laws are expanding access to device repair

**Key Limitations:**
- "Jailbreaking" devices for DIY looping remains in a legal gray area
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

### Current Exemption (2024-2027)

The **9th Triennial DMCA 1201 Rulemaking** concluded in October 2024. The final rule was published on **October 25, 2024**, with exemptions effective **October 28, 2024** through **October 28, 2027**.

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

The DMCA 1201 exemption does **not** provide a safe harbor for DIY automated insulin delivery (AID) systems like Loop, OpenAPS, or AndroidAPS. These activities involve:

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

These are distinct legal questions governed by different bodies of law.

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

---

## Document History

| Date | Change |
|------|--------|
| January 2026 | Initial document created |
| January 2026 | Added cross-reference to Data Rights Primer |

---

## Disclaimer

This document is for informational purposes only and does not constitute legal advice. The legal landscape is complex and evolving. Consult with qualified legal counsel for specific situations.

The authors of this document are not attorneys and make no representations about the accuracy or completeness of this information. Use at your own risk.
