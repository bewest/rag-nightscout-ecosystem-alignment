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

## Release readiness

<!-- chart: release-gates -->

The release is **not ready to tag** until every blocking gate is cleared and a release candidate is
named. The failure or completion state of each gate and its supporting evidence are summarized above;
the release records remain the source of detailed procedures and test boundaries.

The controller-registration milestone in draft [#8857](https://github.com/nightscout/cgm-remote-monitor/pull/8857)
is still within the 16.0.0 entry bar and needs a current-base rebase and retest. The AAPS iOS push
work in [#8810](https://github.com/nightscout/cgm-remote-monitor/pull/8810) may roll to 16.1.0 under
the plan's review condition; draft [#8891](https://github.com/nightscout/cgm-remote-monitor/pull/8891)
is a profile prototype, not a release-critical gate.
Operator-facing release notes remain unwritten until a candidate is named.

## Interpretation limits

- The compatibility matrix measures synthetic request and storage outcomes; it does not prove that
  an individual client's deployed version behaves as its source code suggests.
- Client-impact counts are source-shape matches from the pinned client catalogue, not adoption,
  active-user, or production-traffic counts.
- A measured difference is not automatically a regression: the compatibility report labels intended
  behavior, fixes, and defects separately and links each finding to its evidence.
- PR checks, post-merge branch checks, local full-suite runs, and the synthetic compatibility matrix
  are separate evidence. Passing one does not substitute for another.
