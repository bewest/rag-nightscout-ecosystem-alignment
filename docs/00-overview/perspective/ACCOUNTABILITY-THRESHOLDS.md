# What each activity brings

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Perspective** (part 2 of the overview; [how the overview is organised](../README.md)). Living page,
written 2026-10-16 against this repository at `faafc57c` as "Accountability as an organisation
grows"; widened and retitled 2026-10-17 to cover every entity in the
[control structures](STRUCTURES.md), not only the foundation. It sets out which duties arrive with
each asset an organisation holds and each activity it takes on, how mature programmes put those
duties in place, and the conditions under which a US nonprofit takes on new legal, financial and
insurance duties. Where it interprets, it says so. It makes no request. The evidence for §4 is in
two research notes of 2026-10-17: [Apple's developer program](../../60-research/structures-2026-10-17/apple-accountability.md)
and [vendor programmes and data rights](../../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md).*

*It is a **draft that needs review** by the foundation's accountant (§6), counsel and an insurance
broker (§3, §4, §5) and, for anything touching insulin delivery, a regulatory professional, before
anything rests on it. Thresholds and terms were checked on 2026-10-16 and 2026-10-17 against the
publishers' pages or secondary summaries, as §9 lists; confirm each against the primary source and
the jurisdictions that apply. It describes conditions in general and says nothing about what the
foundation files, holds or has insured today; those are among
[the facts only the foundation can supply](../observations/GOVERNANCE-TODAY.md#7-what-only-the-foundation-can-supply).*

## 1. The question

A common prompt for an organisation to review its duties is the amount of money it handles. Money
is one trigger among several, and for this ecosystem not the most important one. What an
organisation must have in place follows from **what it holds and what it does**: reading someone's
glucose data, hosting it for others, issuing a credential for a pump, commanding insulin delivery,
signing with a manufacturer, taking money. This page lists those triggers and the duties each
brings, for any entity in the proposed structure (the foundation, a hosting operator, a credential
authority, a controller operator), so that the duties a proposal would bring can be seen before it
is adopted rather than after.

## 2. The pillars

*Interpretation.* The duties group into nine pillars. A pillar is triggered by what an organisation
does, not by what it is called. Eight are read from the way Apple's developer program apportions
accountability ([Apple note §6.1](../../60-research/structures-2026-10-17/apple-accountability.md#61-pillars));
the ninth, governance and oversight, is the nonprofit's own.

| pillar | what it answers |
|---|---|
| 1. identity and standing | who is accountable, and can they sign a contract |
| 2. allocation of liability | who answers for harm, up to what, and with what insurance |
| 3. regulatory role | which regulator sees whom as the manufacturer, for which intended use, under what quality system |
| 4. privacy and data protection | consent, purpose, disclosure, retention, breach notice |
| 5. credentials and revocation | who may act, for how long, and how access is withdrawn safely |
| 6. release verification | what is checked before software reaches someone else |
| 7. money | tax, filing, payments, consumer law, paying people |
| 8. continuity and exit | what happens to the people already relying on it when the organisation stops |
| 9. governance and oversight | board duties, conflicts of interest, a public record, and any rules the organisation sets for others |

## 3. Activities and the pillars they trigger

*Interpretation*, except where a row states a rule. Tiers A, B and C are those of
[partner readiness §2](../PARTNER-READINESS.md#2-three-tiers-of-access-and-which-to-ask-for-first).
The last column points at the drawing in which the activity appears.

| activity | pillars | duties it brings | insurance usually considered | in the drawings |
|---|---|---|---|---|
| a person builds and runs software on their own device for their own use | none organisational | the person's own; the platform may impose credential lifetimes (Apple's free tier: 7 days) | none | 3·controller |
| reading device data: glucose, status, history (tier A) | 1, 4, 5; 2 and 3 depending on the claims made for a display or alarm | a privacy notice and purpose limits; accuracy evidence for any health measurement claimed | cyber and privacy liability | 1·proposed, 2·agreement |
| hosting or processing anyone's health data, including complaints and research | 1, 2, 4, 5, 8 | a privacy notice, retention rules, breach response. HIPAA applies only through relationships with covered entities; consumer health services outside HIPAA may fall under the FTC Health Breach Notification Rule (16 CFR Part 318); Washington's My Health My Data Act does not exclude nonprofits; EU residents bring GDPR | cyber and privacy liability | 1·proposed (hosting operators, shared operations) |
| research with identifiable data | 4, 9 | ethics (IRB) review, consent and withdrawal terms, data-use agreements | cyber and privacy; research liability where a partner requires it | — |
| distributing software to other people | 1, 2, 5, 6; 3 if claims are made | an identified publisher, release review, export classification of encryption, end-user terms | technology errors and omissions | 1·proposed (projects), 2·controller-operator |
| operating a service that people's data or therapy depends on: hosting, a relay, a credential authority | 2, 5, 8 | availability, security and incident duties to the people using it; a continuity and succession plan | technology errors and omissions; cyber | 1·proposed, 2·agreement |
| holding or issuing credentials for a device | 1, 2, 5, 8 | custody, rotation, revocation, breach notice, and a defined safe state when a credential expires or is withdrawn | technology errors and omissions; cyber; what the manufacturer's contract requires | 2·agreement, 3·person-loop |
| commanding insulin delivery (tier C) | all nine; 3 and 6 dominate | being, or contracting with, the legal manufacturer of the controller: a regulatory pathway, a quality system, complaint and adverse-event reporting | product liability is a question for counsel | 2·controller-operator |
| signing an agreement with a manufacturer | 1, 2, 9 | the indemnities, insurance minimums and named contacts the contract sets; often an independent security assessment | whatever the contract requires | 1·proposed, 2·agreement |
| taking money for a product or service | 1, 2, 7 | tax, payments and consumer law; trader status in the EU; for a 501(c)(3), whether the income is related to its exempt purpose | — | 1·proposed (hosting operators) |
| a board approving grants and spending | 9 | a duty of care and loyalty in each decision; following the conflict-of-interest policy | directors' and officers' liability (D&O), commonly held at any size | 1·proposed (foundation) |
| holding or moving money | 7 | controls on who can sign and who reconciles | crime or fidelity cover | — |
| events (a hackathon, sponsored travel) | 2 | venue contracts, which often require certificates of insurance | general liability | — |
| receiving money from a company that also seeks something from the organisation | 9 | conflict-of-interest disclosure and recusal; a public record of the arrangement | none specific; D&O covers the decisions | 1·proposed |
| overseeing companies that build on a commons: listing, certifying, setting rules | 2, 9 | published criteria applied the same way to everyone, notice and appeal, and no assumption of the companies' own regulatory duties | D&O; errors and omissions where it certifies (counsel) | 1·proposed (shared operations), 2·cncf |

## 4. How mature programmes put the pillars in place

*Facts as cited; the lessons are interpretation.*

- **Apple prices flat and scales scrutiny by what the app does.** The $99 annual fee is the same for
  every app and waived for nonprofits that sell nothing. What grows with an app's characteristics
  is review depth, approvals and declarations: medical apps get greater scrutiny and must link any
  clearance (guideline 1.4.1); dosage calculators must come from an approved entity or be approved
  (1.4.2); healthcare apps "should be submitted by a legal entity that provides the services, and
  not by an individual developer" (5.1.1(ix)); from 2026-03-26, health and medical apps in the US,
  EU and UK must declare whether they are a regulated medical device. The agreement caps Apple's
  liability at $50 and takes an indemnity from the developer. The fee does not visibly fund
  insurance; the identity checks and the fee make each account accountable, which fits Apple's
  report of 193,035 developer accounts terminated in 2025, 192,702 of them for fraud
  ([Apple note §4–§5](../../60-research/structures-2026-10-17/apple-accountability.md#4-the-reverse-engineered-model-interpretation)).
- **Apple's personal-use tier is a revocable licence.** A free account can build for its own
  devices with 7-day profiles, 3 devices and 3 apps each, for "personal, non-commercial use". It
  carves personal use out of almost every organisational duty, but it rests on a licence Apple can
  withdraw, and its expiry has no defined safe state: Apple disclaims life-critical use.
- **Dexcom offers one agreement on the same terms to everyone, with tiers by scale.** A registered
  developer can serve up to five people with data delayed one hour in the US and three hours
  elsewhere; beyond that comes "a standard, non-negotiable Data Licensing Agreement" and Dexcom's
  review; real-time access is by invitation
  ([vendor note §1.2](../../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#12-dexcom)).
  No other pump or CGM maker publishes a developer programme.
- **The FDA's interoperable routes expect contracts.** The decision summaries for the first ACE pump
  and iAGC describe the manufacturer's plan for sharing interface specifications as covering
  contracts and who handles complaints and adverse-event reporting
  ([vendor note §2](../../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#2-regulatory-interoperability-fda)).

*Interpretation:* across the three, **identity comes before access, the price is the same for
everyone, scrutiny scales with the activity, and liability moves to whoever acts.** Credentials
are issued for a stated time and can be revoked. For a device that delivers insulin, the
programmes found do not supply what [partner readiness §7](../PARTNER-READINESS.md#7-credentials-for-devices-that-require-them)
asks for: previously authorised, safely bounded operation that continues when a credential
service is unreachable.

## 5. The same requirements for anyone

*Interpretation: the author's view, tested against the evidence in §4 and in the
[vendor note §5.2](../../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#52-the-maintainers-working-view-tested).*

The requirements are the same for anyone who takes on an activity: in the US any organisation may
meet them by fulfilling all of them, and in practice that means a legal entity with a quality
system and contracts, usually a company. The FDA
routes are open to any manufacturer that meets the special controls, and Tidepool, a nonprofit,
took the same 510(k) route a company would ([precedents](PRECEDENTS.md#tidepool-loop-20202023)).
Dexcom's agreement is standard and non-negotiable. Washington's health-data act does not exclude
nonprofits. Apple's only nonprofit concession is a fee waiver.

A nonprofit therefore has no advantage in meeting the requirements of §3. Its role is a layer of
oversight, at one level of governance, over the companies that build on a shared commons: CNCF
certifies vendors' offerings against one upstream with the same public tests, and the Open Home
Foundation binds its commercial partners by contract, without either carrying those companies' own
regulatory duties. That role is pillar 9, and it answers the community's need for a party that is
not one of the competitors.

On the engineering side, the cost is falling for everyone: coding agents are used for increasingly
ambitious projects, device connectivity among them (the author's observation; no source read
measures it). That lowers the cost of building an integration. It does not change who is
authorised to use one: device authentication, app attestation and issued credentials are met by
an entity and its agreements, which is the structure drawn in
[1·proposed, 2·agreement and 2·controller-operator](STRUCTURES.md).

## 6. A US nonprofit's own thresholds

The money and staffing conditions that bring the foundation itself new filing, tax and employment
duties, whatever activities it takes on.

### 6.1 Money

| condition | what it brings |
|---|---|
| gross receipts normally above $50,000 | the annual return moves from the Form 990-N e-Postcard to Form 990-EZ |
| gross receipts of $200,000 or more, or total assets of $500,000 or more | the full Form 990. Its Part VI asks whether the organisation has a written conflict-of-interest policy, a whistleblower policy and a document-retention policy, whether the board reviewed the return, and whether it keeps minutes of board and committee meetings at the time they happen |
| asking for donations from residents of a state that requires registration | charitable-solicitation registration and annual reports in that state (Colorado is one) |
| revenue above a state's audit level, where registered | financial statements reviewed or audited by an independent accountant: in New York, a review between $250,000 and $1 million in revenue and an audit above $1 million; in California, an audit at $2 million |
| $1 million or more of federal awards spent in a fiscal year | a Single Audit under 2 CFR 200 Subpart F (the threshold rose from $750,000 for fiscal years beginning on or after 2024-10-01) |

*Interpretation:* at six figures, the money triggers are mostly about filing and disclosure. The
return becomes the public record of the governance practices in Part VI.

### 6.2 Paying people

| condition | what it brings |
|---|---|
| paying anyone for work | deciding whether each person is a contractor or an employee, which follows how the work is controlled, not what the agreement calls it |
| paying someone with influence over the organisation (a director, officer, founder or their family) | the excess-benefit rules (Internal Revenue Code §4958). Pay set by directors without a conflict, using comparable pay data, and recorded at the time, is presumed reasonable (26 CFR 53.4958-6); without that, excess pay can bring penalty taxes on the person and on the managers who approved it |
| the first employee | payroll taxes and filings; workers' compensation in most states (in Texas it is optional for private employers; it depends on the state where the person works); employment-practices insurance becomes relevant |
| paying through a grant made to a project or a third party | a written grant agreement, and records showing the money was used for the exempt purpose |

## 7. Where the proposals meet these conditions

*Interpretation.* Each proposal in part 3, and each entity in the proposed structure, would bring
some of the conditions above if adopted:

| proposal or entity | conditions it would bring |
|---|---|
| [sponsored maintenance team](../SPONSORED-TEAM-PROPOSAL.md) | paying people (§6.2), possibly including people with influence over the foundation; employee or contractor status |
| [datalake pilot](../ECOSYSTEM-PROGRAMME.md#6-commons-c--evidence-research-and-quality) | hosting or processing health data; research with identifiable data |
| [partner readiness](../PARTNER-READINESS.md) | a manufacturer agreement; complaint records that carry health data |
| [operating a shared service](../ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating) | operating a service that people depend on; this is why the programme proposes sponsoring by default |
| [collaboration rules](../COLLABORATION-MODEL.md) | money from companies that also seek something; disclosure; overseeing companies that build on the commons |
| a hosting operator ([1·proposed](STRUCTURES.md#1proposed)) | hosting health data, operating a service, taking money |
| a credential authority operator ([2·agreement](STRUCTURES.md#2agreement)) | holding or issuing credentials, operating a service, a manufacturer agreement |
| a regulated controller operator ([2·controller-operator](STRUCTURES.md#2controller-operator-loop-as-a-service)) | commanding insulin delivery, distributing software, a manufacturer agreement, hosting health data |

The [infrastructure-transition frame](INFRASTRUCTURE-TRANSITION.md) asks when the work of keeping
software current stops being something to leave to whoever has time. This page asks the matching
question for the organisations: which duties arrive with each thing they take on.

## 8. What this frame does not show

- **It is not legal, tax, insurance or regulatory advice.** It lists conditions to raise with
  professionals.
- **Law varies by place.** Registration, audit levels, workers' compensation, privacy law and device
  regulation depend on the states and countries involved.
- **It does not show which conditions apply now.** That depends on facts the foundation and each
  operator hold.
- **Insurance terms vary by policy.** The cover named in §3 is what is usually considered, not what
  any policy includes.
- **Apple's and Dexcom's reasons are inferred.** §4 reads mechanisms from public terms; what either
  company intends, or what its fees pay for, is not in the sources read.

## 9. Points for reviewers to verify

Checked 2026-10-16; each needs confirming at the primary source:

Checked 2026-10-16; each needs confirming at the primary source:

- Form 990-N and 990-EZ thresholds (§6.1): the IRS Form 990-EZ instructions and IRS e-Postcard page.
  The 990-EZ figures were read from IRS form text; the $50,000 e-Postcard figure from a secondary
  guide.
- New York's review and audit levels (§6.1): from accounting-firm and legal-aid summaries of the
  2021–22 change to Executive Law §172-b; confirm with the Attorney General's Charities Bureau.
- California's $2 million audit level (§6.1): Government Code §12586(e); not re-read on 2026-10-16.
- The Single Audit threshold and its effective date (§6.1): 2 CFR 200.501 as revised in 2024; secondary
  sources differ on how the effective date applies to fiscal years that straddle it.
- The excess-benefit presumption (§6.2): 26 CFR 53.4958-6.
- Workers' compensation (§6.2): Texas Labor Code §406.002 for Texas; each other state's rule for the
  state where a worker is.
- The FTC Health Breach Notification Rule (§3): 16 CFR Part 318 as amended in 2024.
- Whether income from a product or service is related to a 501(c)(3)'s exempt purpose (§3): for the
  foundation's accountant.
- Apple's and Dexcom's terms (§4): the points in the
  [Apple note §8](../../60-research/structures-2026-10-17/apple-accountability.md#8-points-for-a-reviewer-to-verify)
  and the [vendor note §7](../../60-research/structures-2026-10-17/vendor-programs-and-data-rights.md#7-points-for-a-reviewer-to-verify),
  read 2026-10-17.
