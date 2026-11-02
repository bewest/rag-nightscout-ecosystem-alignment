# How cgm-remote-monitor 16.0.0 was evaluated

*Contributor- and maintainer-facing release evidence. This colophon evaluates the merged `dev` tree,
not a tagged release candidate. The complete comparison is the
[write-compatibility report](../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html);
release scope and decisions are in [contents](contents.md), [decisions](decisions.md), and
[testing notes](testing-notes.md).*

This is a measurement of synthetic writes against `v15.0.9` and the merged 16.0.0 development tree.
It is not a claim that every deployed site or client has been exercised. The measured tree pins,
runtime, repeated runs, and test-data limitations are recorded with the comparison.
The merged-dev endpoint disables the unique identifier index only so the matrix can seed intentional
duplicate-identifier states; default index startup and duplicate-key races are separate evidence.

**Acceptance reconciliation, 2026-11-02:** the matrix measurement below remains
the November 1 experiment, not a rerun. Informal cohort testing is underway.
The maintainer reports that contributed patches were already tested before
submission and are high-confidence; further live feedback will follow.
Uncollected build/scenario rows are an evidence-recording task, not proof that
the contributions were untested.

## Evidence at a glance

<!-- chart: matrix-runs -->

<!-- chart: origin-split -->

<!-- chart: changed-groups -->

<!-- chart: client-shapes -->

Each endpoint produced 4,916 cells in both runs. The repeats had no differences outside cache/wire;
81 v15.0.9 and 19 merged-dev observations varied only in those excluded fields. All 2,803 changed
cells were classified, with 0 unexplained and no `Defect`-verdict cells; 105 cells are tagged as
bug fixes. The largest group is identifier-format handling (1,886 cells).

The client catalogue contains 15 unique client implementations matched to 120 group-specific
request shapes (11 measured-tier and 109 read-tier matches). These source-based matches do not
represent client adoption, production traffic, or live application tests.

**Compatibility assessment:** high confidence in continued interoperability of
known client contracts without coordinated upgrades; no universal guarantee for
all versions, settings or future features. Legacy v1 replies remain the default,
but intentional re-send/deletion/unit changes are not identical to 15.0.9.
New clients relying on v16-only features still need tested fallback on older
servers. See the [claim-by-claim assessment](../../docs/10-domain/nightscout-v16-ecosystem-deep-dive.md#compatibility-confidence-what-the-record-supports).

## Release readiness

<!-- chart: release-gates -->

**Current integrated test totals, dev `61eb3733`:** hosted top-level `test-ci`
reports 6,323 passing / 3 pending. Adding the separate 319 client-core, 684
browser and 334 Connect cases gives 7,660 passing / 3 pending across suites
counted once, not distinct test identities. The full CI matrix has 31,208
passing / 13 pending executions because suites repeat across environments;
these counts are not additional compatibility-matrix cells.

**Private security integration remains pending:** the previously recorded
BF-72/BF-161 prepared fixes contain
current dev and combined focused tests passed 402; full-suite acceptance is
inconclusive. No private PR existed at that inspection. Advisory association was confirmed, but
the maintainer must route the prepared patches through the advisory's
Compare & pull request workflow, then complete final integrated-tree checks.
No private branch identifiers or payloads are published here.

The release is **not ready to tag** until every blocking gate is cleared and a release candidate is
named. The failure or completion state of each gate and its supporting evidence are summarized above;
the release records remain the source of detailed procedures and test boundaries.

The controller-registration milestone in draft [#8857](https://github.com/nightscout/cgm-remote-monitor/pull/8857)
is still within the 16.0.0 entry bar and needs a current-base rebase and retest. The AAPS iOS push
work in [#8810](https://github.com/nightscout/cgm-remote-monitor/pull/8810) may roll to 16.1.0 under
the plan's review condition; draft [#8891](https://github.com/nightscout/cgm-remote-monitor/pull/8891)
is a profile prototype, not a release-critical gate.
The earlier unwritten-notes status is superseded: [release notes](release-notes.md) and
[cohort guidance](testing-notes.md) are now usable drafts, not final sign-off.
Master's absent 4.4 protection requirement has been removed; retained required
lanes are green, with staging review/policy work ongoing.
#8829 is nonblocking by maintainer decision: neither maintainer reproduced it,
and working DIY and production/service environments are reported.

## Interpretation limits

- The compatibility matrix measures synthetic request and storage outcomes; it does not prove that
  an individual client's deployed version behaves as its source code suggests.
- Client-impact counts are source-shape matches from the pinned client catalogue, not adoption,
  active-user, or production-traffic counts.
- A measured difference is not automatically a regression: the compatibility report labels intended
  behavior, fixes, and defects separately and links each finding to its evidence.
- PR checks, post-merge branch checks, local full-suite runs, and the synthetic compatibility matrix
  are separate evidence. Passing one does not substitute for another.
