# M7 source-paired profile provenance — 2026-11-12

Focused capability checks pass. Full joined acceptance, pilot, capacity,
component scaling and actual Vault key counts remain UNMEASURED in this lane.
No cloud actions, serving image changes, setting mutations or pilot activation
were performed. The coordinator owns the paired campaign and transport guard.

Source is original clean08bce37e9b275f5f43dbb29118b2149c7efb4576 plus
198ad15344bac475e7a5be5bc0db564207a968ab and the compatibility correction
cadcb40bd22fc17b4d134e6b74d3f828d7f2d656. [manifest.json](manifest.json)
pins26 instrument files, content hash
`0c25bf549af0c7b352e9f3f944e49c91b3fe81f736a8bcf98e34622285dc076f`.
The correction appends the fingerprint correctness bit, preserving the existing
oracle/uncertainty assessment positions; no gate expectation was weakened.

The fixture uses an owned immutable core checkout at
`d8d6b547bb17fc91e440bcab48f323a81a6cd66c`. Its nine relevant source blobs
are pinned by the helper. Owned previously installed Node dependencies have the
same package-lock SHA256 as that core:
`6418fe21c18346435f643b8496d6b7ec23c9c6de28f1925c3bb2028eb575e93e`.
Node22.23.4 and Python3.12.3 ran these checks. No peer dependency tree was
mutated. The moving integration checkout advanced during preparation; the
helper refused the mismatched source and testing continued on an owned pinned
checkout rather than substituting the new head.

Reproduced checks:

- [focused.log](focused.log):26 tests pass on exact committedcadcb40 source,
  including the actual pinned status router over local HTTP with synthetic
  authorization, generated k6 status-shape fingerprint, changed-plugin and
  malformed200 refusal, invalid seed, missing observations, dropped/changed
  diagnostic flags, private state override and running-container environment
  fixture checks, fixed2 pilot comparison, real subprocess log timeout and
  byte/global caps, and exited-k6/missing-serving-RSS classification.
- [controls.json](controls.json): removing generated hash comparison makes the
  changed-plugin assertion fail; removing Compose environment equality makes
  the dropped/changed-flag rejection assertion fail; restoring the original
 08bce reducer makes the exited-k6 serving-role assertion fail. Each source
  control exits1 with that semantic symptom; restoring exits0. Controls run in
  an isolated scratch copy. [control-runner.py](control-runner.py) pins the
  actual mutations; the following source correction changed only correctness
  bit placement, outside those controlled paths.
- [diagnostic-regression.log](diagnostic-regression.log):17 existing focused
  real HTTP/stock Socket.IO/CLI controls pass with explicit owned dependency
  lookup. Execution began on198ad source; diagnostic implementation/tests are
  byte-identical in cadcb40. The first attempt omitted NODE_PATH and failed10
  tests because `socket.io-client` could not resolve (and missing observation
  output followed); [setup log](diagnostic-missing-dependency-setup.log) is
  retained. This was fixture setup failure, not inferred product behavior.

The initial reducer hypothesis of a KeyError was refuted. The reproduced defect
is classification: stats-only exited k6 appeared in serving roles despite no
serving snapshot/RSS. The repair retains its measured Docker samples separately
and reports RSS UNMEASURED. A later source-control run reused the initial local
red-log filename; the committed `reducer-original-red.log` is the later
explicit08bce source-ablation execution, not the initial standalone transcript.
No initial transcript is claimed here.

Integration contract is [PROFILE-SEAM.md](../../../tools/mt-bench/m7-joined/PROFILE-SEAM.md)
and static [capabilities.json](../../../tools/mt-bench/m7-joined/capabilities.json).
Actual summary fields are `settingsFingerprint`,
`settingsFingerprintObservation` and `profileSelection` (including canonical
`sha256`). The root must pin the exact selection in final receipt policy and
reserved transport. Same-workload pilot and API replication comparisons refuse
changed fingerprint, diagnostics or topology. Source-default evidence records
six Transit purposes but never turns the schema into a measured key count.
Vault server remains distinct from the unsupported optional Agent overlay.

Limits: workload shapes run under deterministic HTTP mocks, not the stock k6
scheduler; status HTTP is the real isolated router, not the whole serving app;
running-container environment assertions here use a focused inspected-shape
fixture, with real Docker verification wired for the later composed run. No
full serving stack, PG, Vault, throughput or overhead measurement ran here.

Workspace consistency checks are not green: [queue-check.log](queue-check.log)
stops at queue validation because historical gate working directories are
absent in this owned alignment checkout; those gates are UNMEASURED here.
[docs-links.log](docs-links.log) reports7 existing references to the absent
claimed-public-names decision document. No queue/decision/generated-view repair
was attempted in this lane. An earlier unprivileged docs-links attempt failed
at sandboxed `git` subprocess setup; the retained result above is the subsequent
read-only check with git subprocess access.
