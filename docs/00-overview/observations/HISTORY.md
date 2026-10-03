# From a DIY project to shared infrastructure: a chronology of the Nightscout ecosystem

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Observations** (part 1 of the overview; [how the overview is organised](../README.md)). Living
page, assembled 2026-10-02 against this repository at `9b219f31`. It records dates and what
happened; it gives no causes and makes no recommendation. People are named by role. Every row cites
a primary source read on 2026-10-02 or a `git` command run on the clone named in §6, and a row that
could not be established that way is listed in §5 rather than given a date.*

## 1. Origins, 2012–2014

| date | what happened | source |
|---|---|---|
| 2012-10-20 | decocare, a library for talking to Medtronic pumps, has its first commit; it later becomes part of OpenAPS | `git log --reverse`, `openaps/decocare` (`2087ec3`) |
| 2013, autumn | the first D-Data ExChange at Stanford, "the birthplace of the #WeAreNotWaiting hashtag" | [D-Data](https://ddataexchange.com/about/) |
| 2013 | the foundation's homepage: "a father … developed a DIY project called Nightscout" | [nightscoutfoundation.org](https://www.nightscoutfoundation.org/) |
| 2013-10-01 | cgm-remote-monitor's first commits: "First commit of basic index.html that mimics a cgm display" | `git log --reverse`, `nightscout/cgm-remote-monitor` (`90e2a11c`, `4f0c939b`) |
| 2013-12 | DIYPS, a do-it-yourself pancreas system, is created | [diyps.org](https://diyps.org/dana-lewis/) |
| 2014-04 | the CGM in the Cloud Facebook group starts, by the foundation's account: "a spin off from the CGM in the Cloud Facebook group started in April of 2014" | [foundation, FAQ](https://www.nightscoutfoundation.org/faqs) |
| 2014-05-22 | the `nightscout/cgm-remote-monitor` GitHub repository is created, carrying the earlier history | `gh api repos/nightscout/cgm-remote-monitor` |
| 2014-07-29 | cgm-remote-monitor's first tag, 0.3.0 | `git for-each-ref --sort=creatordate refs/tags` |
| 2014-10 | the Nightscout Foundation is "incorporated in October of 2014"; "formed in 2014 as a direct and natural off-shoot of the CGM in the Cloud movement" | [FAQ](https://www.nightscoutfoundation.org/faqs), [about](https://www.nightscoutfoundation.org/about) |
| 2014-11-15 | xDrip's first commit | `git log --reverse`, `NightscoutFoundation/xDrip` (`ee3ece5a9`) |

## 2. The ecosystem grows, 2015–2019

| date | what happened | source |
|---|---|---|
| 2015-02 | "#OpenAPS was created in February 2015" | [diyps.org](https://diyps.org/dana-lewis/) |
| 2015-03-13 | share2nightscout-bridge, which brings Dexcom Share data to Nightscout, has its first commit | `git log --reverse` (`f159cd4`) |
| 2015-04 | the IRS recognises the Nightscout Foundation as a 501(c)(3), EIN 47-2130306: "Tax exemption issued: April 2015" | [ProPublica](https://projects.propublica.org/nonprofits/organizations/472130306) |
| 2015-05-06 | RileyLink, a radio bridge between phones and pumps, has its first commit | `git log --reverse`, `ps2/rileylink` (`3697e99`) |
| 2015-06-29 | oref0, the OpenAPS reference algorithm, has its first commit; first tag 2015-10-19 | `git log --reverse` (`7194614`); tags |
| 2015-08-15 | Loop and LoopKit share a first commit; Loop's first GitHub release, v0.2.0, is 2016-06-04 | `git log --reverse`, `LoopKit/Loop` (`0c5b3b0d`); `gh api …/releases` |
| 2015-10-06 | the CareLink Connect scraper later published as minimed-connect-to-nightscout has its first commit | `git log --reverse` (`2424457`) |
| 2015-11-20 | nightguard, an iOS follower, has its first commit | `git log --reverse` (`1f8e6d5`) |
| 2016-01-15 | the xDrip+ repository is created; the first NightscoutFoundation/xDrip tag is 2016-09-19 | `gh api`; tags |
| 2016-06-04 | AndroidAPS has its first commit | `git log --reverse`, `nightscout/AndroidAPS` (`9b749202fd`) |
| 2017-02-16 | Open Humans' "Nightscout Data Transfer", run by the foundation, launches | [Open Humans](https://www.openhumans.org/activity/nightscout-data-transfer/) |
| 2017-02-24 | the OpenAPS Data Commons on Open Humans launches | [Open Humans](https://www.openhumans.org/activity/openaps-data-commons/) |
| 2018-03-27 | the FDA's De Novo grant for the Dexcom G6 creates the integrated CGM (iCGM) classification | [DEN170088](https://www.accessdata.fda.gov/cdrh_docs/pdf17/DEN170088.pdf) |
| 2018-10-09 | MongoDB announces an agreement to acquire mLab, a database host many Nightscout sites used | [MongoDB](https://www.mongodb.com/company/newsroom/press-releases/mongodb-strengthens-global-cloud-database-with-acquisition-of-mlab) |
| 2018-10-20 | Nightscout Reporter has its first commit | `git log --reverse` (`ae1bc13`) |
| 2018-12-02 | xDrip4iOS has its first commit | `git log --reverse` (`dd408d88`) |
| 2019-02-14 | the FDA authorises the Tandem t:slim X2 as the first alternate-controller-enabled (ACE) pump | [FDA](https://www.fda.gov/news-events/press-announcements/fda-authorizes-first-interoperable-insulin-pump-intended-allow-patients-customize-treatment-through) |
| 2019-05-17 | the FDA warns against using unauthorised devices for diabetes management, including automated insulin dosing systems | [FDA](https://www.fda.gov/news-events/press-announcements/fda-warns-against-use-unauthorized-devices-diabetes-management) |
| 2019-10-09 | API v3 is merged into cgm-remote-monitor (#4250); it first ships in 13.0.0, 2019-12-17 | `git log --diff-filter=A -- lib/api3/index.js` (`2dd576a6`); `git tag --contains` |
| 2019-12-13 | the FDA's De Novo grant for Tandem Control-IQ creates the interoperable automated glycemic controller (iAGC) classification | [DEN190034](https://www.accessdata.fda.gov/cdrh_docs/pdf19/DEN190034.pdf) |

## 3. Hosting, regulation and published evidence, 2020–2024

| date | what happened | source |
|---|---|---|
| 2020-06-01 | LoopFollow has its first commit | `git log --reverse` (`77e7c2f`) |
| 2020-07-14 | mLab's Heroku add-on is discontinued; it is removed from all Heroku apps on 2020-11-10 | [Heroku changelog](https://devcenter.heroku.com/changelog-items/1823) |
| 2020-09-11 | the Nightscout documentation site moves to MkDocs | `git log`, `nightscout/nightscout.github.io` (`b3f97c8`) |
| 2020-09-21 | AndroidAPS's repository is created under the `nightscout` organisation; first release there, 2.7.0, 2020-09-24 | `gh api` |
| 2020-12-17 | Tidepool submits "Tidepool Loop" to the FDA (510(k) K203689) | [FDA database](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K203689) |
| 2021-01-12 | the FreeAPS X code base has its first commit; iAPS and Trio carry the same history (`d6f87f3f`); FreeAPS X's first release is 2021-04-01 | `git log --reverse`; `gh api repos/ivalkou/freeaps/releases` |
| 2021 | the Loop observational study is published: 558 adults and children, six months ([Lum et al.](https://pubmed.ncbi.nlm.nih.gov/33226840/)) | PubMed |
| 2021-11-13 | the international consensus statement on open-source automated insulin delivery is published online in *Lancet Diabetes & Endocrinology* (January 2022 issue) | PubMed PMID 34785000 |
| 2021-12-30 | nightscout-librelink-up has its first commit and release, 1.0.0 | `git log --reverse` (`8ef08a9`); tags |
| 2022-02-16 | the MongoDB 5 driver upgrade is first proposed for cgm-remote-monitor (#7344) | GitHub |
| 2022-08-25 | Heroku announces: "Starting November 28, 2022, we plan to stop offering free product plans and plan to start shutting down free dynos" | [Heroku](https://www.heroku.com/blog/next-chapter/) |
| 2022-08-30 to 10-15 | the Nightscout documentation is reorganised for the end of Heroku's free plan, adding fly.io, Railway, Northflank and Azure pages | `git log`, `nightscout/nightscout.github.io` (`4c0b037`, `763b5b3`, `9c2c35f`, `9ba17c4`) |
| 2022 | the CREATE randomised trial of AndroidAPS with the OpenAPS algorithm is published in the *NEJM* ([Burnside et al.](https://www.nejm.org/doi/full/10.1056/NEJMoa2203913)) | NEJM |
| 2023-01-23 | the FDA clears Tidepool Loop, classified as an interoperable automated glycemic controller | [FDA database](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K203689) |
| 2023-01-26 | LoopCaregiver's repository is created | `gh api` |
| 2023-03-16 | the iAPS repository is created; first release 2023-03-18 | `gh api` |
| 2023-03-22 | nightscout-connect, a vendor-cloud connector for the server, has its first commit | `git log --reverse` (`b6d1c98`) |
| 2023-06-02 | Railway announces plan changes for July–August 2023; the Nightscout documentation records that its free plan was removed | [Railway](https://blog.railway.com/p/pricing-and-plans-migration-guide-2023); `nightscout.github.io` `08dadf56` |
| 2023-10-18 | cgm-remote-monitor 15.0.0 is tagged | tags |
| 2024-03-02 | the Trio repository is created under the `nightscout` organisation; first non-prerelease, v0.2.0, 2024-08-17 | `gh api` |
| 2024-03-18 | Sequel's twiist AID system is cleared, incorporating Tidepool Loop technology | [press release](https://www.globenewswire.com/news-release/2024/03/18/2847675/0/en/Sequel-s-twiist-Automated-Insulin-Delivery-System-Receives-FDA-510-k-Clearance.html) |
| 2024-10-07 | Fly.io's earlier plans close to new customers: "If you purchased a Launch or Scale plan before October 7, 2024, you can remain on those plans" | [Fly.io](https://fly.io/docs/about/discontinued-plans/) |

## 4. More than one server, 2025–2026

| date | what happened | source |
|---|---|---|
| 2025-05-08 | cgm-remote-monitor 15.0.3 is tagged, 561 days after 15.0.2 | tags |
| 2025-11-17 | Nocturne, a second server implementing the Nightscout API, publishes its first commit, "Initial public release of Nocturne" | `git log --reverse`, `nightscout/nocturne` (`b0eeebe0c`) |
| 2026-01-16 | this alignment workspace has its first commit | `git log --reverse` (`bdca28cb`) |
| 2026-04-29 | cgm-remote-monitor 15.0.7 ships the MongoDB 5 driver (#8421); #7344 is closed as superseded on 2026-05-01 | tags; GitHub |
| 2026-09-04 | cgm-remote-monitor 15.0.8 is tagged | tags |
| 2026-09-24 | nightscout-connect 0.1.0 is released | tags |
| 2026-09 to now | 15.0.9 is prepared as a release candidate on `dev`, not yet tagged; its current head and what it waits on are in [ROADMAP §1](../ROADMAP.md#1-the-next-release-1509), and how it was made in the [colophon](../../../releases/cgm-remote-monitor-15.0.9/colophon.md) | ROADMAP §1 |

The cross-project release and contributor record for these years is in
[ECOSYSTEM-EVIDENCE §3](ECOSYSTEM-EVIDENCE.md#3-releases-and-contributors-across-the-main-projects).

## 5. Where sources differ, and what is not established

**Sources that differ.**

- **When the foundation began.** Its FAQ gives incorporation in October 2014; the IRS exemption is
  dated April 2015. These are different events, incorporation and the IRS ruling; no state filing
  was read.
- **First commit and repository date.** Several repositories carry history older than the
  repository itself: cgm-remote-monitor (code from 2013, repository 2014), AndroidAPS (code 2016,
  `nightscout` repository 2020), minimed-connect-to-nightscout (code 2015, `nightscout` repository
  2020) and Trio (FreeAPS X history from 2021, repository 2024). The tables give both dates; neither
  is a founding date.
- **The ACE pump date.** The FDA press release and original order are dated 2019-02-14; a letter of
  2019-12-03 corrects that classification order.
- **The #WeAreNotWaiting origin.** D-Data calls its 2013 meeting the hashtag's birthplace; the
  foundation's homepage describes the foundation as the movement's beginning. This is a difference in
  characterisation, not in dates.

**Not established from a primary source**, so not dated above: the origin of the name Nightscout and
its first public announcement; when Dexcom Share and Abbott LibreLinkUp launched; when mLab shut down
entirely (only the Heroku add-on removal is sourced); Azure's free-tier history for Nightscout.

## 6. How to check

`git` rows were run on the clones under `externals/stack/<owner>__<repo>` (`git log --reverse
--format='%ad %h %s' --date=short | head`, and `git for-each-ref --sort=creatordate refs/tags`);
`gh api` rows on 2026-10-02. Web sources were read with their text extracted on 2026-10-02.
