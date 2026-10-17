# How Apple's developer program apportions accountability

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Research note, 2026-10-17.** Every fact below was read from the cited page on 2026-10-17 unless
it says otherwise; Apple changes these pages often (the App Review Guidelines were last updated the
day before this note), so re-read the source before quoting a figure.*

*Draft for legal review. Wherever this note characterises a contract, a statute or a regulator's
requirement (§2, §3 and the "needs review" column of §6), it is a non-lawyer's reading, to be
checked by counsel, and for §6 also by a regulatory or quality professional, before anyone relies
on it. The specific points for a reviewer are listed in §8.*

It adds to [PARTNER-READINESS](../../00-overview/PARTNER-READINESS.md) (tiers A, B and C of access
to a device, and §7 on credentials), [DIGITAL-RIGHTS](../../DIGITAL-RIGHTS.md) (rights that do
not depend on a manufacturer's permission), [PRECEDENTS](../../00-overview/perspective/PRECEDENTS.md)
(open-source organisations; Apple is not among them because it is a platform owner, not a commons)
and [ECOSYSTEM-PROGRAMME §2b](../../00-overview/ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating)
(sponsoring versus operating). Corrections to the repository's TestFlight and App Store pages are
in §7.

## Terms used

| term | meaning here |
|---|---|
| **Apple Account** | the personal login a person uses for all Apple services |
| **personal team** | what Xcode (Apple's development tool) calls an Apple Account that is not in a paid program; it can install apps the person builds onto their own devices |
| **provisioning profile** | a small signed file from Apple that lists which app, which devices and which special permissions a build may use; without a valid one, an iPhone will not install or launch a self-built app |
| **certificate** | the cryptographic identity a developer signs builds with; Apple issues it and can revoke it |
| **entitlement / capability** | a permission written into the app and the profile that unlocks a system feature (health data, push notifications, alerts that sound when the phone is muted). A **managed** capability is one Apple must grant to the account on request |
| **App Review** | Apple's human and automated review of each app submission against its App Review Guidelines |
| **TestFlight** | Apple's beta-testing service: builds uploaded to Apple are installed by invited testers through the TestFlight app |
| **notarization** | an automated Apple malware and signing check. On the Mac it applies to software distributed outside the Mac App Store; in the EU it is also a reduced review for iPhone apps distributed outside the App Store |
| **D-U-N-S Number** | a nine-digit identifier that Dun & Bradstreet, a business-information company, assigns to an organisation; Apple uses it to check that an organisation exists and is a legal entity |
| **DMA** | the EU Digital Markets Act, a regulation that obliges very large platforms ("gatekeepers") to allow, among other things, other app stores and payment methods |
| **DSA** | the EU Digital Services Act, which among other things obliges online marketplaces to verify and display the contact details of businesses ("traders") selling through them |
| **DPLA** | the Apple Developer Program License Agreement, the contract every paid member signs |
| **indemnify** | to promise to cover another party's losses, including legal costs, if a claim arises from what you did |

## 1. The tiers, as Apple's pages describe them today

### 1.1 Free Apple Account development (personal team)

- **[T1] Limits.** "You can register up to 10 App IDs, which expire after 7 days. You can register
  up to 3 devices, which expire after 7 days. You can install up to 3 apps per device. Provisioning
  profiles that enable apps to be installed on a device will expire 7 days from issuance. You'll
  need to rebuild and reinstall your app to your device after expiration." Apple adds that "you'll
  be required to reprovision your apps to a device periodically."
  ([developer account overview](https://developer.apple.com/help/account/basics/about-your-developer-account);
  the old address `developer.apple.com/support/compare-memberships/` redirects there.)
- **[T2] What the free tier gets.** The same page's table gives free registrants beta Xcode and OS
  releases, on-device testing with Xcode, the forums, Feedback Assistant and Meet with Apple
  activities, and *not* code-level support, Certificates, Identifiers & Profiles, Mac notarization,
  App Store Connect, TestFlight or Xcode Cloud.
- **[T3] Capabilities.** Apple's
  [supported capabilities (iOS)](https://developer.apple.com/help/account/reference/supported-capabilities-ios)
  table lists what a free account ("Apple Developer: … No cost is associated with this agreement and
  developers can't distribute apps") may put in a profile. Available free: App groups, Background
  modes, Data protection, **HealthKit**, HomeKit, Inter-App Audio, Keychain sharing, Maps, Wireless
  Accessory Configuration. Not available free, among others: **Push notifications**, **Time
  Sensitive Notifications**, **Near Field Communication (NFC) Tag Reading**, HealthKit Estimate
  Recalibration, iCloud, Associated domains, App Attest, Sign in with Apple.
- **[T4] Managed capabilities, Critical Alerts among them, are out of reach of the free tier.**
  Requests go through Certificates, Identifiers & Profiles and "your Account Holder will need to
  submit your request" ([capability requests](https://developer.apple.com/help/account/capabilities/capability-requests/));
  Certificates, Identifiers & Profiles is not available to free accounts [T2]. This is an inference
  from two pages; Apple does not state it in one sentence.
- **[T5] The licence.** Free development runs under the **Xcode and Apple SDKs Agreement** (PDF
  marked EA2002; [xcode.pdf](https://www.apple.com/legal/sla/docs/xcode.pdf), file modified
  2026-08-03) and the **Apple Developer Agreement** (dated March 18, 2025;
  [English PDF](https://developer.apple.com/support/downloads/terms/apple-developer-agreement/Apple-Developer-Agreement-20250318-English.pdf)).
  Section 2.2.B of the Xcode agreement lets a developer use provisioning profiles to install apps on
  "a reasonable, limited number of Authorized Test Units … only for internal testing and development
  of Your Applications, or for Your own personal, non-commercial use." Section 2.2.A: "You may not
  distribute any Applications developed using the Apple SDKs (excluding the macOS SDK) absent
  entering into a separate written agreement with Apple." "Provisioning Profiles" are defined as
  "time-limited files" (§1).

### 1.2 Apple Developer Program

- **[P1] Fee.** "The Apple Developer Program annual fee is 99 USD and the Apple Developer Enterprise
  Program annual fee is 299 USD, in local currency where available. Prices may vary by region."
  ([program enrollment](https://developer.apple.com/help/account/membership/program-enrollment/);
  also "$99 annual membership" on [programs](https://developer.apple.com/programs/).)
- **[P2] Individual or organisation.** Enrolment needs an Apple Account with two-factor
  authentication and the legal age of majority. An individual's "personal legal name will be listed
  as the seller on the App Store". An organisation must be a legal entity ("We don't accept DBAs,
  fictitious businesses, trade names, or branches"), have a D-U-N-S Number ("Not required for
  government organizations"), and be enrolled by someone with "the legal authority to bind your
  organization to legal agreements", with a work email on the organisation's domain and a
  functioning public website. Apple may ask for notarised business documents (same page;
  [D-U-N-S](https://developer.apple.com/help/account/membership/D-U-N-S/): "your business must be
  recognized as a legal entity … to enter into the legal terms and obligations of Apple Developer
  Program agreements").
- **[P3] Devices.** Members "can register up to 100 of the following devices, per product family,
  per membership year"; disabling a device does not free a slot; the count is restored only at the
  start of a membership year ([devices overview](https://developer.apple.com/help/account/devices/devices-overview)).
- **[P4] Expiry of membership.** "If your Apple Developer Program membership expires, your apps will
  no longer be available for download … However, your apps will still function for users who have
  already installed or downloaded them." For the Enterprise Program, installed software "will
  continue to run for 90 days after the expiration date"
  ([renewal](https://developer.apple.com/help/account/membership/renewal)).
- **[P5] Check-in with Apple.** For memberships created after June 6, 2021, development- and ad
  hoc-signed apps "check in with the PPQ service when the app is first launched … If the device
  can't successfully make a connection, the app may not launch." An offline profile "valid for 7
  days" is available ([provisioning profile updates](https://developer.apple.com/help/account/provisioning-profiles/provisioning-profile-updates)).

### 1.3 Fee waivers

- **[W1] Eligibility** ([fee waivers](https://developer.apple.com/help/account/membership/fee-waivers/)):
  "Be a legal entity with a status as a nonprofit organization, accredited educational institution,
  or government entity; Not be an individual, sole proprietor, or single-person business; Not have
  signed the Paid Applications Agreement … to offer paid apps or in-app purchases …; and Not otherwise
  sell digital goods or services through any of your apps." A nonprofit "must be officially
  recognized by a relevant authority in your region of operation. For example, the Internal Revenue
  Service in the U.S." The Account Holder re-confirms eligibility at each renewal; the waiver is
  removed if requirements stop being met. The waiver is an option inside organisation enrolment, so
  the D-U-N-S and legal-entity requirements [P2] still apply.
- **[W2] Inconsistency.** The waiver page still says that an approved organisation that has signed
  "the Alternative Terms Addendum for Apps in the EU" will not pay "the Core Technology Fee". Apple's
  EU page [E1] says that addendum was phased out and the Core Technology Fee replaced on October 1,
  2026. The two pages disagree; the EU page is the more recent statement.

### 1.4 Apple Developer Enterprise Program

- **[N1]** ([enterprise](https://developer.apple.com/programs/enterprise/)) "299 USD per membership
  year". "Only for the internal use and distribution of proprietary apps in specific use cases that
  are not adequately addressed with public apps on the App Store, custom apps through Apple Business
  or Ad Hoc distribution, or beta testing through TestFlight." The organisation must "Have 100 or
  more employees", be a legal entity with a D-U-N-S Number, "Have systems in place to ensure only
  employees can download your internal-use apps", and "Participate in and pass Apple's verification
  interview and continuous evaluation process". Verification is repeated at renewal; "Apple reserves
  the right to reject your application at its sole discretion."
- **[N2]** Enterprise members do not get App Store Connect, TestFlight or Xcode Cloud [T2]. The
  Enterprise licence agreement itself was **not read** for this note.

### 1.5 TestFlight

- **[F1]** "You can test a build for up to 90 days." "Your build becomes unavailable for testers
  after 90 days." Up to 10,000 external testers and up to 100 internal testers who are App Store
  Connect users with a role on the team. "When you add the first build of your app to a group, the
  build gets sent to App Review … A review is required only for the first build. Subsequent builds
  may not require a full review." At upload, Apple asks the developer to determine whether app
  encryption documentation is needed for US export compliance ([TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview)).
- **[F2]** "You can share up to 100 builds." External testing needs "your first build already
  approved by App Review for TestFlight. Your builds are automatically sent for review once they're
  added to a group" ([TestFlight](https://developer.apple.com/testflight/)). Whether every external
  build is reviewed, or only the first, is stated differently on the two pages.
- **[F3] Contract terms** (DPLA §7.4): internal distribution is "solely for their internal use in
  testing, evaluating and/or developing Your Applications"; testers may not be charged; and "You may
  not use TestFlight for purposes that are not related to improving the quality, performance, or
  usability of pre-release versions of Your Application (e.g., continuous distribution of demo
  versions of Your Application in an attempt to circumvent the App Store …)".

### 1.6 Entitlements that need approval

- **[X1] Critical Alerts.** Apple's entitlement documentation: an app with
  `com.apple.developer.usernotifications.critical-alerts` "can request [criticalAlert] authorization
  to receive push notifications that cause the system to play a sound even when the app is locked,
  muted, or a person uses Do Not Disturb focus"; the authorisation-options documentation says
  "Critical alerts require a special entitlement issued by Apple." The request form
  (`developer.apple.com/contact/request/notifications-critical-alerts-entitlement/`) requires
  sign-in and **was not read**; Apple's approval criteria are therefore **not verified** here.
  Secondary sources describe them as health, medical, home-security and public-safety uses.
- **[X2] HealthKit** is a self-service capability, available even to free accounts [T3]; the
  obligations attach through the contract and the guidelines (§2, [R3]–[R5]), not through approval.
- **[X3]** The guidelines' introduction: "Some features and technologies that are not generally
  available to developers may be offered as an entitlement for limited use cases."

### 1.7 App Review Guidelines on health

From the [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), "Last
Updated: October 16, 2026". Sections marked on the page as applying to both App Store review and
notarization review are marked (N).

- **[R1] 1.4.1 (N)** "Medical apps that could provide inaccurate data or information, or that could
  be used for diagnosing or treating patients may be reviewed with greater scrutiny." Apps "must
  clearly disclose data and methodology to support accuracy claims relating to health
  measurements"; apps claiming to measure "blood glucose levels … using only the sensors on the
  device are not permitted"; "Apps should remind users to check with a doctor"; "If your medical app
  has received regulatory clearance, please submit a link to that documentation with your app."
- **[R2] 1.4.2 (N)** "Drug dosage calculators must come from the drug manufacturer, a hospital,
  university, health insurance company, pharmacy or other approved entity, or receive approval by
  the FDA or one of its international counterparts. Given the potential harm to patients, we need to
  be sure that the app will be supported and updated over the long term."
- **[R3] 5.1.1(ix) (N)** "Apps that provide services in highly regulated fields (such as … healthcare
  …) or that require sensitive user information should be submitted by a legal entity that provides
  the services, and not by an individual developer." 5.1.1(i) requires a privacy policy that
  explains retention, deletion and how consent is revoked.
- **[R4] 5.1.2(vi) (N)** Data from HealthKit and the Clinical Health Records API "may not be used for
  marketing, advertising or use-based data mining, including by third parties."
- **[R5] 5.1.3 (N)** Health data may not be used or disclosed to third parties for advertising or
  data mining; apps "must not write false or inaccurate data into HealthKit … and may not store
  personal health information in iCloud"; research apps need participant consent and "approval from
  an independent ethics review board".
- **[R6] Documentation.** "Medical apps that make diagnostic or treatment claims: Regulatory
  clearance for each country or region where the app is available, such as FDA, CE, or CFDA
  documentation, or a supporting test report or peer-reviewed study"
  ([complete review](https://developer.apple.com/help/app-review/before-submitting-for-review/complete-review)).
- **[R7] Regulated medical device status (new in 2026).** Announced March 26, 2026: apps distributed
  in the EEA, UK or US whose primary or secondary category is Health & Fitness or Medical, or that
  mark "frequent" medical or treatment information in the age-rating questionnaire, must declare
  whether they are a regulated medical device. Required for new apps from that date; existing apps
  "must provide a status by early 2027", after which updates cannot be submitted
  ([news](https://developer.apple.com/news/?id=nyqbfz1y)). A "Yes" requires an EU SRN or FDA
  Owner/Operator Number, an instructions-for-use URL, the indications-for-use or intended-purpose
  statement and safety information, all shown on the product page
  ([declare status](https://developer.apple.com/help/app-store-connect/manage-app-information/declare-regulated-medical-device-status)).
  Self-certification under the EU MDR or UK regulations counts as "Yes".

### 1.8 Notarization on the Mac

- **[M1]** "Notarization of macOS software is not App Review. The Apple notary service is an
  automated system that scans your software for malicious content, checks for code-signing issues".
  Since macOS 10.15, "all software built after June 1, 2019, and distributed with Developer ID must
  be notarized." The service "maintains an audit trail of the software distributed using your
  signing key", and tickets can be revoked
  ([notarizing macOS software](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)).
  Notarization is not available to free accounts [T2].

### 1.9 The EU: alternative distribution and trader status

- **[E1] Unified terms from October 1, 2026.** "The Apple Developer Program License Agreement,
  updated August 18, 2026, introduced new business terms … Effective October 1, 2026 … The Core
  Technology Fee, a per-install fee for developers who achieve extraordinary scale, has been
  replaced by the Core Technology Commission, a simple 5% commission on digital transactions in apps
  distributed outside the App Store." The Initial Acquisition Fee and Store Services Fee are
  eliminated; the earlier EU addenda are "superseded by Attachment 14"
  ([apps in the EU](https://developer.apple.com/support/dma-and-apps-in-the-eu/), which now
  redirects to `/support/apps-in-the-eu`). The commission applies to sales; the page lists no
  per-install charge for free apps.
- **[E2] Notarization for iPhone apps.** "A baseline review that applies to all apps, regardless of
  their distribution channel, focused on platform policies for security and privacy", combining
  "automated checks and human review", against the Notarization Review Guidelines, a subset of the
  App Review Guidelines (accuracy, functionality, safety, security, privacy). "If Apple determines
  that an app contains known malware after it's been installed, it will be prevented from launching."
- **[E3] Authorised marketplaces and Web Distribution** need Apple's authorisation. Eligibility (any
  one of): a "moderate financial-stability bar as scored by Dun & Bradstreet"; publicly traded;
  venture funding; an audit by a licensed accountant; "a government entity, educational institution,
  or nonprofit approved for a fee waiver"; a "stand-by letter of credit of USD 1,000,000"; or one
  million first annual installs. "Companies are no longer required to have a legal entity or be
  established in the EU." A marketplace operator holding a fee waiver may distribute only apps from
  developers holding the same waiver [W1].
- **[E4] EU App Store commission** (same page): 26% on Apple In-App Purchase (15% for Small Business
  Program participants and subscriptions after year one); 20% or 10% with alternative payment
  processing.
- **[E5] DSA trader status.** "Articles 30 and 31 of the Digital Services Act (DSA) require Apple to
  verify and display trader contact information for all traders distributing apps on the App Store
  in the European Union". Every developer must declare a status, even without EU distribution;
  "Apple can't determine whether you're a trader"; a hobbyist "may not be considered a trader";
  "if you have a legal status associated with a business activity, that would suggest you may be a
  trader." Individuals who are traders publish an address, phone and email; organisations publish
  the D-U-N-S address. Non-traders' EU customers are told consumer-protection rights will not apply
  ([DSA trader requirements](https://developer.apple.com/help/app-store-connect/manage-compliance-information/manage-european-union-digital-services-act-trader-requirements)).

### 1.10 Small Business Program

- **[S1]** "A reduced commission rate of 15% on paid apps and Apple In-App Purchases" for developers
  with up to 1 million USD in proceeds in the prior calendar year, counted together with any
  "Associated Developer Accounts" (over 50% common ownership); requires accepting the Paid Apps
  agreement ([Small Business Program](https://developer.apple.com/app-store/small-business-program/)).
  The standard non-EU rate was not read for this note.

### 1.11 Age assurance

- **[G1]** Texas SB2420: from January 1, 2026, new Texas accounts face "age assurance and parent or
  guardian consent on behalf of minors under the age of 18 for downloads, purchases, and significant
  changes associated with an app"; "It's the developer's responsibility to determine when there's a
  significant change to their app" ([Nov 4, 2025](https://developer.apple.com/news/?id=2ezb6jhj)).
  On June 3, 2026, after "a recent court ruling lifting an injunction", the requirements took effect
  June 4, 2026 ([news](https://developer.apple.com/news/?id=sg176nne)). Utah (May 6, 2026) and
  Louisiana (July 1, 2026) use the same tools; 18+ apps are blocked in Australia, Brazil and
  Singapore without adult confirmation from February 24, 2026
  ([news](https://developer.apple.com/news/?id=f5zj08ey)). The status of the Texas law after
  June 3, 2026 was **not verified**.

## 2. What each tier obliges, and what Apple takes on

The agreements are on Apple's [agreements page](https://developer.apple.com/support/terms/): DPLA
"Last update: August 18, 2026"; Paid Applications Agreement (Schedules 2 and 3) "December 17, 2025";
Apple Developer Agreement March 18, 2025. DPLA text read from
[the DPLA page](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/).

| topic | free tier (Xcode and Apple SDKs Agreement; Apple Developer Agreement) | paid program (DPLA) |
|---|---|---|
| **who is responsible** | "You … will be solely responsible for all costs, expenses, losses and liabilities incurred … Your related development and limited distribution efforts" (Xcode §2.1); "solely responsible for all user assistance, warranty and support" (§2.2.B) | Schedule 1, Exhibit B, item 5: the end-user licence must say "You, not Apple, are responsible for addressing any claims … including … (i) product liability claims; (ii) any claim that the Licensed Application fails to conform to any applicable legal or regulatory requirement"; ad hoc distribution: "solely responsible for all user assistance, warranty and support" (§7.3) |
| **indemnification** | developer indemnifies Apple for breach and for "Your use of the Apple Software … Your development of Applications, or Your loading of Applications" (Xcode §4) | seven heads of claim, including any claim by end users, parents or authorities "regarding Your Covered Products" (§10(v)) |
| **life-critical use** | Apple software "is not intended for use in the development of Applications in which errors … could lead to death, personal injury, or severe physical or environmental damage", and the developer indemnifies Apple for such use (Xcode §4) | the same acknowledgement and indemnity (§10, second paragraph); §12: not "suitable for use in situations … where errors, delays, failures or inaccuracies … could lead to death, personal injury" |
| **limit of Apple's liability** | "In no event shall Apple's total liability … exceed the amount of fifty dollars ($50.00)" (Xcode §7; Apple Developer Agreement §14) | the same $50 cap, "other than as may be required by applicable law in cases involving personal injury" (§13) |
| **regulatory** | no regulatory clause found in the free agreements | §3.3.2: comply with FDA and other regulators; "You agree that You will not seek any regulatory marketing permissions or make any determinations that may result in any Apple products being deemed regulated or that may impose any obligations or limitations on Apple"; market "only for its cleared or approved intended use"; provide clearance documents on request; notify Apple of regulatory complaints, after which "Apple may remove Your Application" |
| **privacy and health data** | Apple Developer Agreement §19 covers Apple's handling of the developer's own data | §3.3.3: consent before collection; a privacy policy; protect data "from unauthorized use, disclosure or access"; notify users of a breach; HealthKit only "for health, motion, and/or fitness purposes" and never disclosed to third parties without express consent (§3.3.3(H)); not use Apple services "to create, receive, maintain or transmit any … 'protected health information'" or in a way that makes Apple a HIPAA "business associate" |
| **security of signing keys** | — (Xcode manages free-tier certificates) | §5.1: "solely responsible for preventing any unauthorized person or organization from having access to Your Apple Certificates and keys"; "e.g., You will not upload Your Apple Certificate for App Store distribution to a cloud repository for use by a third party"; notify Apple of compromise "immediately" |
| **revocation** | "Apple reserves the right to revoke, disable or suspend any Provisioning Profiles … at any time, in its sole discretion" (Xcode §5); provisioning profiles revocable "e.g., if Apple suspects fraudulent or malicious activity" (§2.3) | §5.4: Apple may revoke any certificate "at any time, in its sole discretion", with eight example grounds ending "(h) Apple has reason to believe that such action is prudent or necessary", and "may notify end users"; §5.3: notarization tickets revocable; "If Apple revokes Your Ticket or Your Apple Certificate, then Your Application may no longer run on macOS" |
| **termination** | rights end "automatically … without notice" on non-compliance (Xcode §5); Apple "may terminate or suspend you … at any time in Apple's sole discretion" (Apple Developer Agreement §10) | one-year term renewing on payment (§11.1); termination on notice after a 30-day cure period, or at once for confidentiality breach, insolvency, sanctions or fraud (§11.2); "Either party may terminate this Agreement for its convenience … effective 30 days after providing the other party with written notice" |
| **export** | Apple Developer Agreement §16; Xcode §8.4 | §14.8: no export to embargoed places or listed parties; on request, disclose "ultimate beneficial ownership, such as individuals with substantial control or 25% or greater ownership"; §5.3: no notarization uploads of software needing export authorisation |
| **fees** | none | annual fee, "non-refundable", must be paid to submit (§8) |
| **changes** | Apple may modify the agreement "at its discretion" (Apple Developer Agreement §9) | "Apple may change the Program Requirements or the terms of this Agreement at any time"; not accepting means suspension or termination (§4) |
| **publicity** | — | no public statements about the agreement "without Apple's express prior written approval" (§9.4) |

**What Apple takes on.** From the same sources: reviewing submissions and, "if … selected by
Apple", signing and distributing them (DPLA, Purpose); running notarization, with the caveat that
its checks "should not be relied upon for malware detection or security verification of any kind"
(§5.3); verifying and displaying EU trader details, a duty the DSA places on Apple [E5]; displaying
a declared medical-device status [R7]; providing age signals [G1]; operating certificate issuance
and revocation (§5.4; Apple's certificate policy at apple.com/certificateauthority); and, for
In-App Purchase, payment processing and tax support [E4]. Apple's 2025
[App Store Transparency Report](https://www.apple.com/legal/app-store/transparency/2025/) gives the
scale: 9,100,620 submissions reviewed, 2,093,244 rejected, 60,597,750 registered developers (all
tiers), and 193,035 developer accounts terminated, 192,702 of them under "DPLA 3.2(f) — Fraud".
The report cites export control as "DPLA 4.8"; in the current DPLA export control is §14.8 and §4
is "Changes to Program Requirements or Terms". The report's numbering may follow an older version;
not verified.

## 3. What Apple discloses about why

Apple's FY2025 annual report ([10-K filed 2025-10-31](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm))
and latest quarterly report ([10-Q filed 2026-07-31](https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm))
were read through a summarising fetch, not in full; quotations below should be re-checked against
the filings.

- **[K1] Scrutiny.** Under the heading "The technology industry, including, in some instances, the
  Company, is subject to intense media, political and regulatory scrutiny, which exposes the Company
  to increasing regulation, government investigations, legal actions and penalties": Apple "is the
  subject of investigations in Europe and other jurisdictions relating to App Store terms and
  conditions"; its DMA compliance plan "has been challenged by the Commission and may be challenged
  further by private litigants. The DMA provides for significant fines and penalties for
  noncompliance."
- **[K2] DMA.** "On April 23, 2025, the Commission fined the Company €500 million in the Article 5(4)
  Investigation", with a cease-and-desist order to remove restrictions "that prevent developers from
  steering users to alternative distribution channels outside the App Store"; Apple has appealed. An
  Article 6(4) investigation was at preliminary findings; a final violation finding allows "fines up
  to 10% of the Company's annual worldwide net sales" (10-Q, Legal Proceedings).
- **[K3] Epic Games.** On April 30, 2025 a district court found Apple in violation of a 2021
  injunction. On December 11, 2025 the Ninth Circuit upheld the 2025 injunction in part and held
  "the Company can charge some commission on link-out purchases"; on June 30, 2026 the Supreme Court
  "granted the Company's petition to review the applicable legal standard for civil contempt"
  (10-Q).
- **[K4] Minors.** Apple is "subject to new and changing laws, regulations and other legal
  obligations regarding online safety, including enhanced protections for minors and mandatory age
  verification requirements", which "can also result in significant penalties and fines, and legal
  liability" (10-Q, Risk Factors). Apple's own developer news on Texas SB2420 states that it is
  "concerned about the potential implications of laws like SB2420"
  ([Nov 4, 2025](https://developer.apple.com/news/?id=2ezb6jhj)).
- **[K5] Health.** Under the product-defects risk factor: "These risks may increase as the Company's
  products are introduced into specialized applications, including health", and "the Company can be
  exposed to product liability claims" (10-K).
- **[K6] Commission, not fees.** The 10-Q risk factors tie revenue risk to commission: if developers
  use alternative distribution and payment, "the Company may earn a lower commission on such sales,
  or may not earn a commission at all". Program-fee revenue was not found broken out in the passages
  read; whether any filing reports it is **not verified**.

## 4. The reverse-engineered model *(interpretation)*

This section is interpretation. Each row cites the facts it rests on.

| asset or activity Apple supports | obligation or exposure it triggers | mechanism in the program | who bears the cost |
|---|---|---|---|
| a person running their own code on their own device | little regulatory exposure for Apple; risk that free signing becomes a distribution channel; account fraud | 7-day profiles, 3 devices, 3 apps, 10 App IDs [T1]; no push, NFC, notarization or TestFlight [T2][T3]; "personal, non-commercial use" and no distribution [T5]; revocable at any time (Xcode §2.3, §5); $50 cap and full indemnity (§2) | the person: rebuilding every 7 days and all liability; Apple: running the signing service |
| identified distribution to other people | consumer protection, malware, fraud, a seller of record | annual fee [P1]; identity and legal-entity checks, D-U-N-S, binding authority [P2]; App Review [§2 "what Apple takes on"]; certificate custody duties and revocation (§5.1, §5.4); 100-device cap [P3]; PPQ check-in [P5] | developer: fee, verification, compliance; Apple: review and enforcement (193,035 terminations in 2025) |
| pre-release testing on others' devices | unreviewed or lightly reviewed code reaching up to 10,000 people | review of the first external build [F1][F2]; 90-day build expiry [F1]; no charge to testers and no "continuous distribution" [F3] | developer: rebuilding within 90 days; Apple: beta review |
| an organisation's private, internal apps | public distribution outside review | 100 employees, legal entity, interview, "continuous evaluation", re-verification [N1]; no TestFlight or App Store Connect [N2]; 90-day run-on after expiry [P4]; $299 | organisation |
| health data | HIPAA, consumer privacy law, Apple's own position on privacy | HealthKit purpose limits and no third-party disclosure without consent (§3.3.3(H)); no protected health information through Apple services and never making Apple a business associate (§3.3.3); guidelines 5.1.2(vi), 5.1.3 [R4][R5] | developer |
| medical function or claims | FDA, EU MDR and UK device regulation; the risk that Apple's own products are "deemed regulated" | §3.3.2; scrutiny and clearance documents [R1][R6]; dosing calculators only from approved entities or with approval [R2]; legal entity, not individual [R3]; public device-status declaration [R7]; life-critical disclaimers and indemnity (§10, §12) | developer, entirely; Apple disclaims the use |
| an alert that overrides silence | misuse of an interruption that bypasses the user's settings | managed entitlement granted on request by the Account Holder [X1][T4] | developer: application; Apple: case-by-case review (criteria not verified) |
| taking money | tax, payments, consumer law, EU trader rules | Paid Applications Agreement; commission [E4][S1]; DSA trader verification and publication [E5]; loss of fee waiver [W1] | developer and customers through commission; Apple's DSA duty met with the developer's data |
| distribution outside the App Store in the EU | DMA obligations; security of devices | notarization for iOS [E2]; authorised marketplaces with financial-standing tests [E3]; 5% commission on sales [E1]; malware kill switch [E2] | developer and marketplace; Apple runs notarization |
| code-signing infrastructure | key compromise; malware signed with a real identity | custody duties and breach notice (§5.1); revocation for eight reasons (§5.4); Mac notarization audit trail [M1]; PPQ check-in [P5] | developer for custody; Apple for issuance and revocation |
| minors | age-assurance laws in several states and countries | age-category signals and consent APIs; developer decides "significant change" [G1] | developer for in-app duties; Apple for account-level assurance |
| export and sanctions | US export and sanctions law | §14.8 warranties and beneficial-ownership disclosure; export-compliance documentation at upload [F1]; termination on sanctions (§11.2) | developer |

The pattern across the rows: **the price is flat, and the scrutiny scales.** The $99 fee does not
change with risk; what scales with the characteristics of the app is review depth, approvals,
declarations and documents, and the contract moves the resulting liability to the developer.

## 5. Testing the hypothesis

The working hypothesis had five parts. The evidence for and against each:

**(a) Tiers of cost and commitment.** *Supported.* Free (no fee, 7-day profiles, no distribution
[T1][T5]), paid ($99, identity and entity checks [P1][P2]), enterprise ($299, 100 employees,
interview, continuous evaluation [N1]), and add-ons that change the commercial terms (fee waiver
[W1], Small Business Program [S1], EU terms [E1]). Commitment rises with each tier: legal identity,
binding authority, then an organisation's internal controls.

**(b) Fees pay for insurance, review and compliance.** *Not supported by public evidence, and
partly contradicted.*
- Apple does not say what the fee pays for. Program-fee revenue was not found in the filings read
  [K6], and the number of paying members is not published in the sources read (the 60.6 million
  "registered developers" includes free accounts). Whether the fee covers review cost cannot be
  computed from public sources.
- The fee is the same for a game and a medical app, so it is not priced to risk.
- Apple waives the fee for qualifying nonprofits, schools and governments that do not sell [W1].
  A fee that funded review would be odd to waive for apps that still need review.
- The commission is what Apple's filings treat as the revenue at stake [K6][K1]–[K3].
- On insurance, the contracts point the other way: Apple does not insure developers' risk; it caps
  its own liability at $50, disclaims life-critical use and takes an indemnity (§2). The developer
  carries the risk and any insurance for it. Whether Apple buys insurance for App Store activities
  is not disclosed in the sources read.
- *Counter-argument, fairly put:* a fee plus D-U-N-S and identity checks is a cheap filter against
  fraud at scale, and fraud is by far the main ground for terminating accounts (192,702 of 193,035
  in 2025). Read that way, the fee pays for *accountability*, by making each account cost something
  and tying it to a verified person or entity, rather than for review hours. This fits the evidence
  better than cost recovery, but Apple does not state it either.

**(c) Requirements are triggered by the characteristics of the assets and activities.**
*Strongly supported.* Health data triggers §3.3.3(H) and 5.1.3; medical claims trigger §3.3.2, 1.4.1,
the clearance documents and the device-status declaration; dosing triggers 1.4.2; regulated fields
trigger "legal entity, not individual"; selling triggers the Paid Applications Agreement, trader
status and loss of the fee waiver; overriding silence triggers a managed entitlement; minors trigger
age assurance; the EU triggers notarization and marketplace rules. The triggers are mostly declared
by the developer (category, age questionnaire, trader self-assessment, device status), and Apple
says plainly that some it cannot decide: "Apple can't determine whether you're a trader" [E5].

**(d) Device vendors will need comparable programmes, up and down.** *Consistent with the evidence,
but Apple is not proof of it.* Apple's program runs from governance (contract, entity checks,
termination) down to technology (profile lifetimes, PPQ check-in, revocation). A device maker
issuing credentials to third-party apps faces the same questions, set out in
[PARTNER-READINESS §7](../../00-overview/PARTNER-READINESS.md#7-credentials-for-devices-that-require-them).
The difference is that Apple's own regulatory position depends on staying *out* of device
regulation (§3.3.2), while a pump or CGM manufacturer is the regulated party, so its program will
carry duties (complaint handling, reporting) that Apple's does not.

**(e) The free tier as a model for data rights.** *Partly.*
- What fits: the tier exists for a person's "own personal, non-commercial use" [T5]; it needs no
  fee, no legal entity and no review; and the person is both developer and user, so no one else's
  accountability is engaged.
- What does not fit: it is a licence, not a right. Apple may revoke it "at any time, in its sole
  discretion" and end it without notice (Xcode §2.3, §5; Apple Developer Agreement §10). It expires
  every 7 days by design [T1]. It excludes push notifications, NFC and managed capabilities such as
  Critical Alerts [T3][T4], which apps that read sensors or raise alarms commonly use.
- Purpose of the time limit: *not determinable from public sources.* The accountability reading:
  short-lived, revocable trust for unverified identities, plus the agreement's fraud language (§2.3).
  The business reading: the limits make the paid program the practical route for anyone who needs
  reliability. Apple states neither purpose. One page suggests a looser use: the guidelines'
  introduction says an app "you just want to show to family and friends" can be installed "on a
  device for free", while the Xcode agreement limits free provisioning to devices "owned or
  controlled by You" (or by Authorized Developers for testing) and "Your own personal, non-commercial
  use". The two texts are not reconciled on Apple's pages.

## 6. Transfer to diabetes *(interpretation)*

This section is interpretation, kept generic. It names no company. "Needs review" marks points
that must go to counsel (L), a regulatory or quality professional (R), or both.

### 6.1 Pillars

Reading §4 as categories gives eight pillars of organisational requirement. A pillar is triggered
by what the organisation does, not by what it is called.

| pillar | what it answers | Apple's form of it |
|---|---|---|
| 1. identity and standing | who is accountable, and can they sign a contract | Apple Account; legal entity, D-U-N-S, binding authority |
| 2. allocation of liability | who answers for harm, and up to what | indemnity, $50 cap, life-critical disclaimer, end-user licence terms |
| 3. regulatory role | which regulator sees whom as the manufacturer, and for what intended use | §3.3.2; clearance documents; device-status declaration |
| 4. privacy and data protection | consent, purpose, disclosure, breach notice, retention | §3.3.3; guidelines 5.1.x |
| 5. credentials and revocation | who may act, for how long, and how access is withdrawn | certificates, profiles, expiry, PPQ, revocation |
| 6. release verification | what is checked before software reaches someone else | App Review, TestFlight review, notarization |
| 7. commerce | tax, payments, consumer law, trader status | Paid Applications Agreement, commission, DSA |
| 8. continuity and exit | what happens to people already relying on it | apps keep working after membership expiry [P4]; 30-day termination notice |

### 6.2 Activities and the pillars they trigger

Tiers A, B and C are those of [PARTNER-READINESS §2](../../00-overview/PARTNER-READINESS.md#2-three-tiers-of-access-and-which-to-ask-for-first).

| activity | pillars triggered | the nearest Apple mechanism | needs review |
|---|---|---|---|
| **a person builds and runs software on their own device for their own use** | none beyond the person's own; 5 only as far as the platform imposes it | free tier [T1][T5] | L: whether the person's rights here rest on law (see [DIGITAL-RIGHTS](../../DIGITAL-RIGHTS.md)) or only on a licence that can be withdrawn |
| **reads glucose data** (tier A) | 1, 4, 5, and 2 for display accuracy; 3 depending on claims | HealthKit purpose limits; 1.4.1 accuracy and methodology | R: whether a display or alarm function, with the claims made for it, is a regulated device function in each market; L: privacy regime for the data |
| **holds credentials for an insulin pump** | 1, 2, 5 at its most demanding, 8 | §5.1 custody duties; §5.4 revocation; breach notice | L, R: who may hold a manufacturer-issued credential, how compromise is reported, and what state the pump enters if a credential expires or is revoked. Apple's free tier stops an app launching after 7 days [T1]; PARTNER-READINESS §7 asks instead that previously authorised, safely bounded local operation continue |
| **commands insulin delivery** (tier C) | all eight; 3 and 6 dominate | §3.3.2; 1.4.2 (dosing only from approved entities or with approval); 5.1.1(ix) (legal entity, not individual); device-status declaration [R7] | R: regulatory pathway, quality system, complaint and adverse-event reporting; L: product liability and insurance, and how a manufacturer's contract would allocate them |
| **hosts health data for others** | 1, 2, 4, 5, 8 | §3.3.3 including the "business associate" clause | L: HIPAA (only through covered-entity relationships), the FTC Health Breach Notification Rule, GDPR and state laws; breach duties; retention; what happens to the data when the host stops |
| **distributes software to others** | 1, 2, 5, 6; 3 if claims are made | ADP identity checks; App Review; TestFlight 90-day builds and review; notarization; export answer on upload | L: export classification of encryption; the end-user terms; R: whether release review counts as part of a quality system |
| **takes money** | 1, 2, 7 | Paid Applications Agreement; trader status; loss of fee waiver [W1] | L: tax and charitable-status consequences for a 501(c)(3); consumer law; trader status in the EU |

### 6.3 What the Apple model suggests for an ecosystem or vendor programme

Interpretation, offered as questions for the discussion rather than recommendations:

1. **Price flat, scrutiny by trigger.** Apple charges everyone the same and scales review by declared
   characteristics. A programme could ask each participant to declare the activities in §6.2 and
   attach the pillars to the declaration, rather than pricing or naming tiers by organisation type.
2. **A personal-use tier with a stated basis.** Apple's free tier shows that a platform can carve
   out personal use with almost no organisational duty. For data rights, the difference that
   matters is whether that carve-out is a revocable licence (Apple's) or rests on a right and on
   agreement terms the person can enforce
   ([PARTNER-READINESS §4](../../00-overview/PARTNER-READINESS.md#4-what-the-ecosystem-needs-from-an-agreement):
   "revocation by process").
3. **Lifetimes chosen for safety, not only for control.** Apple's lifetimes are 7 days (free), 90
   days (TestFlight), one year (membership), and installed App Store apps keep working after
   membership ends [P4]. For a device that delivers insulin, expiry and revocation need a defined
   safe state, which Apple's model does not provide because it disclaims life-critical use.
4. **Keep the issuer out of the regulated role, or accept it.** Apple's §3.3.2 forbids developers
   from making Apple "deemed regulated". A foundation sponsoring a programme faces the same choice
   that [ECOSYSTEM-PROGRAMME §2b](../../00-overview/ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating)
   names: sponsor without operating, or operate with a named operator, contract and insurance.
5. **Legal entity where regulated.** Guideline 5.1.1(ix) expects healthcare apps from "a legal entity
   that provides the services, and not … an individual developer". Any agreement with a
   manufacturer is likely to expect the same, which is the "who is accountable?" row of
   PARTNER-READINESS §3.

## 7. Corrections to existing repository pages

### 7.1 [testflight-distribution-infrastructure.md](../../10-domain/testflight-distribution-infrastructure.md) (dated 2026-01-31)

1. **TestFlight limits are missing.** Add: builds expire after 90 days [F1]; up to 100 internal
   testers who must hold an App Store Connect role, up to 10,000 external testers, up to 100 builds
   [F1][F2]; the first external build goes to App Review [F1]. The 90-day expiry is the reason
   scheduled rebuilds are needed.
2. **"Apple Developer account (free or paid)" for self-build needs the free-tier limits.** A free
   account gets 7-day profiles, 3 devices, 3 apps per device and 10 App IDs [T1], and cannot use
   Push notifications, Time Sensitive Notifications or NFC Tag Reading [T3], nor request Critical
   Alerts [T4]. The page's entitlement table (§3.1) lists NFC and Critical Alerts without saying they
   need a paid membership.
3. **"Certs expire after 1 year"** is not stated on the Apple pages read for this note; mark it
   unverified or cite a source. The page omits that expiry of a *membership* does not stop installed
   App Store apps [P4], whereas TestFlight builds stop after 90 days regardless.
4. **App Store requirements (§1.1) are incomplete.** "No therapeutic claims" is not Apple's wording.
   Add guidelines 1.4.1 (accuracy methodology, clearance link), 1.4.2 (dosage calculators), 5.1.1(ix)
   (legal entity for healthcare), the regulated medical device declaration due for existing apps
   "by early 2027" [R7], and the DSA trader declaration [E5].
5. **Fee.** $99 is current [P1]; add that prices vary by region, and that a recognised nonprofit
   enrolling as an organisation may apply for a waiver if it does not sell [W1].
6. **"Mac with Xcode 15+"** is several major versions behind the current Xcode; Apple's current
   minimum for uploads was not read for this note.
7. **Certificate custody.** The browser-build pattern stores distribution certificates in a private
   repository and uses them on hosted CI runners. DPLA §5.1 says a developer "will not upload Your
   Apple Certificate for App Store distribution to a cloud repository for use by a third party" and
   may not give distribution certificates to a service provider. How that applies when the developer
   stores their own certificate for their own builds is a question for counsel (§8), not a finding.
8. **Development and ad hoc builds check in with Apple** on first launch for teams created after
   June 6, 2021 [P5].

### 7.2 [app-store-pathway-analysis.md](../../10-domain/app-store-pathway-analysis.md) (dated 2026-01-31)

1. **"Guideline 5.1: Safety"** is mis-numbered. Safety is section 1 and physical harm is 1.4; 5.1 is
   Privacy. The quoted wording ("Apps that could cause physical harm may be rejected") is a
   paraphrase of 1.4 ("If your app behaves in a way that risks physical harm, we may reject it").
2. **"Apple won't distribute unapproved medical devices"** is not Apple's wording. The relevant texts
   are 1.4.1, 1.4.2, 5.1.1(ix), DPLA §3.3.2 and the device-status declaration [R1]–[R3][R7]; cite
   those.
3. **Critical Alerts approval criteria** ("Glucose monitoring apps: typically approved") are not on
   any Apple page read; the request form needs sign-in [X1]. Mark as unverified.

## 8. Points for a reviewer to verify

**For counsel:**

1. The characterisation of DPLA §§3.3.2, 3.3.3, 5.1, 5.4, 10, 11, 12, 13 and 14.8, and of Xcode and
   Apple SDKs Agreement §§2.2, 2.3, 4, 5 and 7, against the versions current on the day of review.
2. Whether the $50 cap and the life-critical disclaimers are enforceable as written, given the
   carve-out "other than as may be required by applicable law in cases involving personal injury".
3. Whether storing App Store distribution certificates in a developer's own private repository, used
   by hosted CI runners for that developer's own builds, is consistent with DPLA §5.1 [§7.1 item 7].
4. Whether long-term personal use of one's own TestFlight build fits DPLA §7.4 ("solely for their
   internal use in testing, evaluating and/or developing") [F3].
5. Whether a free-tier build installed on a family member's device is within Xcode §2.2.B, given the
   guidelines' "family and friends" sentence [§5(e)].
6. For a 501(c)(3): the fee-waiver conditions [W1], DSA trader status [E5], and whether taking money
   in any form through an app would end the waiver.
7. The privacy regimes named in §6.2 and their application to hosted data.
8. The Apple Developer Enterprise Program License Agreement, not read here.

**For a regulatory or quality professional:**

9. Whether reading or displaying glucose data, with the claims an app makes, is a regulated device
   function in the US, EU and UK, and how that answer would change the device-status declaration
   [R7].
10. What a credential lifetime and revocation design must guarantee for a delivery device (§6.3
    item 3; PARTNER-READINESS §7).
11. Whether release verification (§6.1 pillar 6) can serve as part of a quality system record.

**Facts to re-check at the source:**

12. The 10-K and 10-Q passages in §3, which were read through a summarising fetch.
13. The Critical Alerts approval criteria (request form not read).
14. The status of Texas SB2420 after June 3, 2026.
15. Whether any Apple filing reports program-fee revenue or paying-member counts.
16. Whether the transparency report's "DPLA 4.8" reference is to an older numbering.
17. Whether the fee-waiver page has been updated to match the EU terms of October 1, 2026 [W2].

## Sources

All read 2026-10-17.

| source | URL |
|---|---|
| Developer account overview (free tier limits, membership table) | https://developer.apple.com/help/account/basics/about-your-developer-account |
| Programs overview | https://developer.apple.com/help/account/membership/programs-overview |
| Apple Developer Program | https://developer.apple.com/programs/ |
| Program enrollment | https://developer.apple.com/help/account/membership/program-enrollment/ |
| D-U-N-S Number | https://developer.apple.com/help/account/membership/D-U-N-S/ |
| Fee waivers | https://developer.apple.com/help/account/membership/fee-waivers/ |
| Renewal | https://developer.apple.com/help/account/membership/renewal |
| Devices overview | https://developer.apple.com/help/account/devices/devices-overview |
| Provisioning profile updates | https://developer.apple.com/help/account/provisioning-profiles/provisioning-profile-updates |
| Certificates overview | https://developer.apple.com/help/account/certificates/certificates-overview |
| Supported capabilities (iOS) | https://developer.apple.com/help/account/reference/supported-capabilities-ios |
| Capability requests | https://developer.apple.com/help/account/capabilities/capability-requests/ |
| Enterprise Program | https://developer.apple.com/programs/enterprise/ |
| TestFlight overview | https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview |
| TestFlight | https://developer.apple.com/testflight/ |
| Critical Alerts entitlement (documentation JSON) | https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.usernotifications.critical-alerts |
| UNAuthorizationOptions.criticalAlert | https://developer.apple.com/documentation/usernotifications/unauthorizationoptions/criticalalert |
| App Review Guidelines | https://developer.apple.com/app-store/review/guidelines/ |
| Complete review (regulated-field documents) | https://developer.apple.com/help/app-review/before-submitting-for-review/complete-review |
| Regulated medical device status (help) | https://developer.apple.com/help/app-store-connect/manage-app-information/declare-regulated-medical-device-status |
| Regulated medical device status (news, 2026-03-26) | https://developer.apple.com/news/?id=nyqbfz1y |
| Notarizing macOS software | https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution |
| Apps in the EU (DMA) | https://developer.apple.com/support/dma-and-apps-in-the-eu/ |
| DSA trader requirements | https://developer.apple.com/help/app-store-connect/manage-compliance-information/manage-european-union-digital-services-act-trader-requirements |
| Small Business Program | https://developer.apple.com/app-store/small-business-program/ |
| Agreements and guidelines (versions, dates) | https://developer.apple.com/support/terms/ |
| Apple Developer Program License Agreement | https://developer.apple.com/support/terms/apple-developer-program-license-agreement/ |
| Apple Developer Agreement (2025-03-18) | https://developer.apple.com/support/downloads/terms/apple-developer-agreement/Apple-Developer-Agreement-20250318-English.pdf |
| Xcode and Apple SDKs Agreement (EA2002) | https://www.apple.com/legal/sla/docs/xcode.pdf |
| App Store Transparency Report 2025 | https://www.apple.com/legal/app-store/transparency/2025/ |
| Texas SB2420 news (2025-10-08, 2025-11-04, 2026-06-03) | https://developer.apple.com/news/?id=btkirlj8 ; https://developer.apple.com/news/?id=2ezb6jhj ; https://developer.apple.com/news/?id=sg176nne |
| Age requirements in other regions (2026-02-24) | https://developer.apple.com/news/?id=f5zj08ey |
| Apple 10-K, fiscal 2025 | https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm |
| Apple 10-Q, quarter ended 2026-06-27 | https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm |

Not read: the Critical Alerts request form (sign-in required); the Apple Developer Enterprise
Program License Agreement; the Paid Applications Agreement text; the full 10-K and 10-Q (read through
a summarising fetch).
