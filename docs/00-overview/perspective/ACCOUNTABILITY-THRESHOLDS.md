# Accountability as an organisation grows

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Perspective** (part 2 of the overview; [how the overview is organised](../README.md)). Living page,
written 2026-10-16 against this repository at `faafc57c`. It sets out the conditions under which a
US nonprofit takes on new legal, financial and insurance duties, as a frame for reading the
proposals in part 3. Where it interprets, it says so. It makes no request.*

*It is a **draft that needs review** by the foundation's accountant (§2, §3) and counsel and an
insurance broker (§4, §5) before anything rests on it. Thresholds were checked on 2026-10-16
against the publishers' forms or secondary summaries, as §7 lists; confirm each against the primary
source and the states that apply. It describes conditions in general and says nothing about what
the foundation files, holds or has insured today; those are among
[the facts only the foundation can supply](../observations/GOVERNANCE-TODAY.md#7-what-only-the-foundation-can-supply).*

## 1. The question

A common prompt for a nonprofit to review its insurance is the amount of money it handles. Money
is one trigger among several. This page lists the others, so that the duties a proposal would bring
can be seen before it is adopted rather than after.

## 2. Money

| condition | what it brings |
|---|---|
| gross receipts normally above $50,000 | the annual return moves from the Form 990-N e-Postcard to Form 990-EZ |
| gross receipts of $200,000 or more, or total assets of $500,000 or more | the full Form 990. Its Part VI asks whether the organisation has a written conflict-of-interest policy, a whistleblower policy and a document-retention policy, whether the board reviewed the return, and whether it keeps minutes of board and committee meetings at the time they happen |
| asking for donations from residents of a state that requires registration | charitable-solicitation registration and annual reports in that state (Colorado is one) |
| revenue above a state's audit level, where registered | financial statements reviewed or audited by an independent accountant: in New York, a review between $250,000 and $1 million in revenue and an audit above $1 million; in California, an audit at $2 million |
| $1 million or more of federal awards spent in a fiscal year | a Single Audit under 2 CFR 200 Subpart F (the threshold rose from $750,000 for fiscal years beginning on or after 2024-10-01) |

*Interpretation:* at six figures, the money triggers are mostly about filing and disclosure. The
return becomes the public record of the governance practices in Part VI.

## 3. Paying people

| condition | what it brings |
|---|---|
| paying anyone for work | deciding whether each person is a contractor or an employee, which follows how the work is controlled, not what the agreement calls it |
| paying someone with influence over the organisation (a director, officer, founder or their family) | the excess-benefit rules (Internal Revenue Code §4958). Pay set by directors without a conflict, using comparable pay data, and recorded at the time, is presumed reasonable (26 CFR 53.4958-6); without that, excess pay can bring penalty taxes on the person and on the managers who approved it |
| the first employee | payroll taxes and filings; workers' compensation in most states (in Texas it is optional for private employers; it depends on the state where the person works); employment-practices insurance becomes relevant |
| paying through a grant made to a project or a third party | a written grant agreement, and records showing the money was used for the exempt purpose |

## 4. Activities

*Interpretation:* these are the triggers most likely to matter for this ecosystem. They depend on
what the organisation does, not on how much it holds.

| activity | duties it brings | insurance usually considered |
|---|---|---|
| a board approving grants and spending | a duty of care and loyalty in each decision; following the conflict-of-interest policy | directors' and officers' liability (D&O), commonly held at any size |
| holding or moving money | controls on who can sign and who reconciles | crime or fidelity cover |
| events (a hackathon, sponsored travel) | venue contracts, which often require certificates of insurance | general liability |
| holding or processing anyone's data, including health data in complaints or research | a privacy notice, retention rules, breach response. HIPAA applies only through relationships with covered entities; consumer health services outside HIPAA may fall under the FTC Health Breach Notification Rule (16 CFR Part 318); EU residents bring GDPR | cyber and privacy liability |
| operating a service that people's data or therapy depends on: hosting, a relay, a credential authority | availability, security and incident duties to the people using it; a continuity and succession plan | technology errors and omissions (professional liability); cyber |
| signing an agreement with a manufacturer | indemnities, insurance minimums and named contacts the contract sets; often an independent security assessment | whatever the contract requires; product liability is a question for counsel |
| research with identifiable data | ethics (IRB) review, consent and withdrawal terms, data-use agreements | cyber and privacy; research liability where a partner requires it |
| receiving money from a company that also seeks something from the organisation | conflict-of-interest disclosure and recusal; a public record of the arrangement | none specific; D&O covers the decisions |

## 5. Where the proposals meet these conditions

*Interpretation.* Each proposal in part 3 would bring some of the conditions above if adopted:

| proposal | conditions it would bring |
|---|---|
| [sponsored maintenance team](../SPONSORED-TEAM-PROPOSAL.md) | paying people (§3), possibly including people with influence over the foundation; employee or contractor status |
| [datalake pilot](../ECOSYSTEM-PROGRAMME.md#6-layer-4--the-research-and-quality-commons) | holding or processing health data; research with identifiable data |
| [partner readiness](../PARTNER-READINESS.md) | a manufacturer agreement; complaint records that carry health data |
| [operating a shared service](../ECOSYSTEM-PROGRAMME.md#2b-sponsoring-and-operating) | operating a service that people depend on; this is why the programme proposes sponsoring by default |
| [collaboration rules](../COLLABORATION-MODEL.md) | money from companies that also seek something; disclosure |

The [infrastructure-transition frame](INFRASTRUCTURE-TRANSITION.md) asks when the work of keeping
software current stops being something to leave to whoever has time. This page asks the matching
question for the organisation: which duties arrive with each thing it takes on.

## 6. What this frame does not show

- **It is not legal, tax or insurance advice.** It lists conditions to raise with professionals.
- **State law varies.** Registration, audit levels and workers' compensation depend on the states
  where the foundation is registered, solicits donations and has workers.
- **It does not show which conditions apply now.** That depends on facts the foundation holds.
- **Insurance terms vary by policy.** The cover named in §4 is what is usually considered, not what
  any policy includes.

## 7. Points for reviewers to verify

Checked 2026-10-16; each needs confirming at the primary source:

- Form 990-N and 990-EZ thresholds (§2): the IRS Form 990-EZ instructions and IRS e-Postcard page.
  The 990-EZ figures were read from IRS form text; the $50,000 e-Postcard figure from a secondary
  guide.
- New York's review and audit levels (§2): from accounting-firm and legal-aid summaries of the
  2021–22 change to Executive Law §172-b; confirm with the Attorney General's Charities Bureau.
- California's $2 million audit level (§2): Government Code §12586(e); not re-read on 2026-10-16.
- The Single Audit threshold and its effective date (§2): 2 CFR 200.501 as revised in 2024; secondary
  sources differ on how the effective date applies to fiscal years that straddle it.
- The excess-benefit presumption (§3): 26 CFR 53.4958-6.
- Workers' compensation (§3): Texas Labor Code §406.002 for Texas; each other state's rule for the
  state where a worker is.
- The FTC Health Breach Notification Rule (§4): 16 CFR Part 318 as amended in 2024.
