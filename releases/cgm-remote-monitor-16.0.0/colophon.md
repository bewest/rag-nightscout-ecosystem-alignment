# How cgm-remote-monitor 16.0.0 was evaluated

*November 1–2 evaluation of synthetic writes against `v15.0.9` and
development commit `497d08c9`. The [closing candidate record](contents.md#closing-candidate-2026-11-24)
gives the later development head, staging checks and outstanding acceptance.
The [write-compatibility report](../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html)
gives the measured trees, runtime, repeats and test-data limits.*

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

## Release readiness at the November 2 review

<!-- chart: release-gates -->

**November 1 integrated test totals (read-derived from CI on `61eb3733`).** Top-level `test-ci`
reports 6,323 passing / 3 pending. Adding the separate 319 client-core, 684
browser and 334 Connect cases gives 7,660 passing / 3 pending across suites
counted once, not distinct test identities. The full CI matrix has 31,208
passing / 13 pending executions because suites repeat across environments;
these counts are not additional compatibility-matrix cells.

**November 2 security review (read-derived).** The prepared BF-72/BF-161 fixes contained
`61eb3733`. The combined focused tests passed 402 cases. The full-suite result was inconclusive. No private PR existed at that inspection. Advisory association was confirmed, but
the maintainer must route the prepared patches through the advisory's
Compare & pull request workflow, then complete final integrated-tree checks.
No private branch identifiers or payloads are published here.

At that review, placement remained open for controller registration (#8857),
AAPS iOS background pushes (#8810) and the single-site profile prototype (#8891).
The maintainer recorded #8829 as nonblocking. For the current candidate, see
the [staging and acceptance findings](contents.md#closing-candidate-2026-11-24)
and [cohort guide](testing-notes.md).

## Interpretation limits

- The compatibility matrix measures synthetic request and storage outcomes; it does not prove that
  an individual client's deployed version behaves as its source code suggests.
- Client-impact counts are source-shape matches from the pinned client catalogue, not adoption,
  active-user, or production-traffic counts.
- A measured difference is not automatically a regression: the compatibility report labels intended
  behavior, fixes, and defects separately and links each finding to its evidence.
- PR checks, post-merge branch checks, local full-suite runs, and the synthetic compatibility matrix
  are separate evidence. Passing one does not substitute for another.
