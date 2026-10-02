# How decisions are made today across the Nightscout ecosystem

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Observations** (part 1 of the overview; [how the overview is organised](../README.md)). Living
page, measured 2026-10-02 against this repository at `bdd84c4b`. It describes what can be read from
public sources and the repositories' own settings; it does not assess any of it. Repository rows
come from `gh api`, run with a maintainer's token (which can read some settings the public cannot,
noted where it matters). Foundation rows quote its public pages, read the same day. People are
named by role. §6 lists where we looked and found nothing, and §7 the facts only the foundation can
supply.*

## 1. Who decides in each project

Each project decides for itself what it merges and releases. Measured per repository:

| repository | owner | licence (GitHub / file) | pull requests merged in the 12 months to 2026-10-02 / distinct accounts that merged them | releases / latest / distinct release authors | rules on the default branch |
|---|---|---|---|---|---|
| nightscout/cgm-remote-monitor | organisation | AGPL-3.0 | 284 / 2 | 66 / 2026-09-04 / 7 | one approving review, three status checks, pushes limited to two teams |
| nightscout/nightscout-connect | organisation | AGPL-3.0 | 23 / 2 | 1 / 2026-07-07 / 1 | none |
| nightscout/nocturne | organisation | none / no file (README: AGPL-3.0, with commercial licensing offered) | 1,111 / 3 | 15 / 2026-09-11 / 2 | one ruleset, enforcement disabled |
| nightscout/AndroidAPS | organisation | AGPL-3.0 | 508 / 1 | 33 / 2026-08-02 / 1 | one approving review |
| nightscout/Trio | organisation | MIT | 330 / 10 | 22 / 2026-09-20 / 3 | three approving reviews including a code owner, applied to administrators; a ruleset blocking force-pushes |
| nightscout/nightguard | organisation | AGPL-3.0 | 6 / 1 | 40 / 2026-09-29 / 1 | a ruleset blocking deletion and force-pushes |
| nightscout/share2nightscout-bridge | organisation | none / no file (`package.json`: GPL-3.0-only) | 1 / 1 | 11 / 2026-02-27 / 3 | none |
| nightscout/minimed-connect-to-nightscout | organisation | MIT | 1 / 1 | none (31 tags) | none |
| nightscout/nightscout.github.io (documentation) | organisation | GPL-2.0 | 12 / 2 | none | none |
| NightscoutFoundation/xDrip | organisation | GPL-3.0 | 132 / 1 | 890 / 2026-10-02 / 1 | protected; details not readable |
| LoopKit/Loop | organisation | NOASSERTION / MIT "with exceptions for frameworks and graphics" | 63 / 3 | 66 / 2024-10-09 / 2 | protected; details not readable |
| LoopKit/LoopKit | organisation | MIT | 40 / 2 | 43 / 2019-12-31 / 2 | protected; details not readable |
| LoopKit/LoopWorkspace | organisation | none / no file | 51 / 3 | 15 / 2026-09-20 / 1 | protected; details not readable |
| LoopKit/LoopCaregiver | organisation | none / no file | 9 / 2 | none | none |
| loopandlearn/LoopFollow | organisation | AGPL-3.0 | 191 / 3 | 51 / 2026-09-20 / 2 | one approving review including a code owner, status checks |
| openaps/oref0 | organisation | MIT | 1 / 1 | 19 / 2022-06-19 / 3 | one approving review |
| JohanDegraeve/xdripswift | personal account | GPL-3.0 | 24 / 2 | 95 / 2026-09-22 / 2 | protected; details not readable |
| timoschlueter/nightscout-librelink-up | personal account | MIT | 11 / 1 | 43 / 2026-03-04 / 1 | protected; details not readable |
| zreptil/nightscout-reporter | personal account | BSD-3-Clause (file opens with third-party notices) | 0 / 0 | none | none |
| tidepool-org/platform | organisation | BSD-2-Clause | 61 / 5 | 39 / 2019-04-12 / 2 | protected; details not readable |

Commands: `gh api repos/<o>/<r>`, `…/releases`, `…/rulesets`, `…/branches/<default>/protection`;
`gh pr list --state merged --search 'merged:>2025-10-02' --json mergedBy` (GraphQL pagination for
Nocturne, which has more than 1,000). "Not readable" means the token has no admin rights there.

**GitHub organisations** (`gh api orgs/<o>`): `nightscout` (created 2014-05-21, 39 public
repositories, 9 public members), `NightscoutFoundation` (2015-06-01, 8, 1), `LoopKit` (2016-08-26,
39, 1), `loopandlearn` (2023-06-06, 58, 1), `openaps` (2015-04-12, 19, 3). None of the five has a
`.github` repository, so none sets organisation-wide default files.

## 2. Written project governance

| file | repositories, of the 20 above, that have it (root, `.github/` or `docs/`) |
|---|---|
| GOVERNANCE | none |
| SECURITY policy | none, apart from tidepool-org/platform through its organisation's default |
| CODE_OF_CONDUCT | Trio, Loop, LoopKit |
| CODEOWNERS | Trio, LoopFollow |
| CONTRIBUTING | cgm-remote-monitor, AndroidAPS, Trio, xDrip, LoopWorkspace, oref0, and tidepool-org/platform through its organisation |

**Reporting a security problem.** GitHub's private vulnerability reporting is enabled on
cgm-remote-monitor, Nocturne, AndroidAPS and tidepool-org/platform, and not on the other 16.

**Where discussion happens**, as linked from each README: Discord (cgm-remote-monitor, AndroidAPS,
Trio, the documentation), Facebook (Trio, LoopFollow), Zulip (Loop, LoopKit), Gitter (nightguard,
share2nightscout-bridge), GitHub Discussions (xDrip; also switched on for Nocturne, xdripswift and
nightscout-librelink-up without a README link).

## 3. The Nightscout Foundation

| subject | what its public pages say | source |
|---|---|---|
| purpose | "The Nightscout Foundation exists to encourage and support the creation of open source technology projects that enhance the lives of people with Type 1 Diabetes and those who love them. This includes fundraising, advocacy, and direct software and hardware development." | [about](https://www.nightscoutfoundation.org/about) |
| origin | "a spin off from the CGM in the Cloud Facebook group started in April of 2014, incorporated in October of 2014"; "registered as a non-profit corporation in the state of Texas and in Colorado" | [FAQ](https://www.nightscoutfoundation.org/faqs) |
| tax status | 501(c)(3), EIN 47-2130306, "Tax exemption issued: April 2015" | [ProPublica](https://projects.propublica.org/nonprofits/organizations/472130306) |
| board | six positions listed: a president, two founding directors and three directors | [leadership](https://www.nightscoutfoundation.org/leadership) |
| governance documents | "Corporate Bylaws", "Conflict of Interest Policy" and "IRS 501(c)3 Letter of Determination", linked as Google Drive files; without signing in they redirect to a sign-in page | [foundation info](https://www.nightscoutfoundation.org/foundation-info) |
| requests for support | funds "Build Tools", "Learning & Education", "Developer Infrastructure" and "Community Access"; "Submit your request / Our committee reviews your application / We follow up to discuss next steps and support", through a Google Form | [resource request](https://www.nightscoutfoundation.org/resource-request) |
| other contact routes | an email link for volunteering, an email link for stories, and an on-site contact form | how you can help, why, contact pages |
| events | "HackDiabetes is an annual hackathon run by The Nightscout Foundation", with published sponsorship levels; the foundation "sponsors 7 Open Source Developers" to attend ATTD 2026 | [events](https://www.nightscoutfoundation.org/new-events), [hackathon](https://www.nightscoutfoundation.org/diabetes-hackathon) |
| recognition | Visionary Awards, with published criteria such as "Must be open-source and released into the wild" and "Must not be a member of the Board of Directors, or a direct family relation" | [awards](https://www.nightscoutfoundation.org/visionary-awards) |
| projects supported | it "has more recently supported development of … Loop, Trio, and OpenAPS/AndroidAPS" | [home](https://www.nightscoutfoundation.org/) |
| code and imagery | "A formal organization also allows the open source IP to have a home. Nightscout code, imagery, and videos can be protected and licensed to fund the projects we support." The logo is under a Creative Commons licence; "You may not sell logo items without Foundation Board permission." | [FAQ](https://www.nightscoutfoundation.org/faqs), [logos](https://www.nightscoutfoundation.org/logos) |
| trademark | USPTO searches for "nightscout", "nightscout foundation" and "cgm in the cloud" found no registration owned by the foundation (one unrelated, abandoned 2015 application by another company) | USPTO trademark search, 2026-10-02 |

## 4. The shared documentation's provider listing

The Nightscout documentation's "Nightscout as a Service" section lists nine hosted providers, each
linking to its own site (`nightscout/nightscout.github.io`, branch `source`, `docs/index.md`, last
changed at `9b5afad2` on 2026-08-07). Its introduction: "If you want to save time and avoid the need
to maintain a DIY solution, you have many providers." Providers are added by pull request; the two
most recent additions (#247, 2026-03-13, and #249, 2026-05-24) were merged with no review recorded.
The repository publishes no criteria for being listed and no rule for the order. The first entry is
the company founded by this repository's author.

## 5. Where the foundation's statements and the repositories differ

- The FAQ says the code "will continue to be available under a GPL". The repositories in §1 carry
  AGPL-3.0, GPL-2.0, GPL-3.0, MIT and BSD licences, and four carry no licence file; two of the MIT
  repositories (Trio, minimed-connect-to-nightscout) are in the `nightscout` organisation.
- The purpose statement on the homepage begins "support the creation of technological solutions";
  the about page says "open source technology projects".
- One board member is "President" on the leadership page and "(Chair)" on the FAQ.

## 6. Where we looked and found nothing

- **Foundation decision records.** The 18 pages linked from nightscoutfoundation.org, its awards
  page, and the 24 non-blog paths in its `sitemap.xml`: no meeting minutes, annual reports,
  financial statements, decision records, grant policy or sponsorship policy. The resource-request
  page names no committee members and no review criteria.
- **Financial filings.** ProPublica's Nonprofit Explorer has no Form 990 data for EIN 47-2130306.
- **Repository governance files.** As in §2, searched at the root, `.github/` and `docs/` of each
  of the 20 repositories and through GitHub's community-profile endpoint.
- **Provider listing criteria.** The documentation's provider section and every `.md` file in that
  repository, searched for listing criteria or instructions.
- **A shared body for decisions that cross projects.** None is named on the foundation's pages or in
  the governance files above.

## 7. What only the foundation can supply

These are not public, or not readable without signing in. The page records them as open, not as
absent:

1. Whether the bylaws and the conflict-of-interest policy are meant to be public, and if so a
   readable copy.
2. Who sits on the resource-request committee, what it weighs, and where its decisions are recorded.
3. How spending is approved, and whether a yearly summary of income and spending is published.
4. Which domains, accounts, repositories and marks the foundation holds, and which belong to
   individuals or other organisations.
5. How a sponsorship or partnership is agreed, and where it is recorded.
