# Receipt profile selection and core-only campaign attribution — 2026-11-12

Focused validator capability passes on exact committed
`16c78776a27fb183a1953d2d59b9c499283b7ab2`. This lane's original validator
history was merged with original profile evidence history
`a82bbc54f4db878d0839b498200a7a5729b494c3` at
`a21974824a2d02e7df71be63dc33f6f3c9c535d1`; no peer worktree was edited.
[instrument.json](instrument.json) pins the source files and reviewed producer
content hash. Earlier evidence records remain unchanged.

[focused.log](focused.log) records47 passing focused checks. These are synthetic
ephemeral record fixtures, not an actual campaign PASS receipt. The new checks
require coordinator-pinned `profileSelection` equal to the actual producer's
settings/diagnostics/topology object and canonical hash. Every selected cell
requires positive clean fingerprint observations. Same-source ON/OFF diagnostics,
changed settings, changed worker topology or missing observations refuse even
when all independent artifact hashes are refreshed. API1/2 FAIL comparison
cells remain allowed beside a passing adopted3k/API4 target when otherwise
complete; this does not turn10k stretch into an adopted prerequisite.

[controls.json](controls.json) and its [runner](control-runner.py) record three
isolated checker-source ablations: remove actual selection equality, remove
positive-clean observation requirements, remove same-core functional campaign
fence. Each makes its substantive refusal oracle fail (exit1); restoring the
check returns exit0. [Import failure](producer-helper-import-failure.log) is the
measured pre-repair integration boundary: the updated producer's lazy helper
could not resolve from the gate cwd. The repaired scoped import restores cwd
independence; the full-ladder CLI fixture verifies no bytecode/files are written.
[docs-links.log](docs-links.log) reports27 checked,0 failing in this coherent
owned validator/profile checkout. The earlier profile-only branch's missing-doc
result retains its original source attribution.

The functional campaign boundary was read directly from the immutable original
worker in nightscout-deploy instrument
`3d8ca353f973433021ae2086cd643d03da5fb3a4`, worker blob
`d39a96a7412e246e77b7619565965e665fce0e81`. Its command runner uses the core
checkout as cwd (line143); campaign verifies the exact core HEAD and installs,
bundles and tests that core (lines253–315). Deployment hash appears only in
source authorization/metadata (lines63/74/235); no deployment binding execution
was found. This is read-derived scope evidence, not a rerun of that worker.

Optional coordinator `functionalCampaignPair` therefore defaults to primary
pair, permits an explicitly approved captured deployment metadata hash, and
always requires exactly the primary core. Tests preserve raw campaign metadata:
missing/wrong approved deployment pin refuses, any different core refuses, and
an independently pinned final paired-image proof still refuses an earlier
binding attribution. No equivalent-core inference or relabeling is allowed.
The coordinator must retain the required final image/native binding criteria in
its expectation; this core-only result does not supply those proofs.

Root integration: ordinary-merge this original history, then pin the exact
actual `profileSelection` and optional approved `functionalCampaignPair` in the
reviewed expected manifest. Retain required final source/image/native criteria,
explicit pending policy and every required tier/corpus/control. There is no
queue/release/decision/generated-view edit and no full campaign, capacity or
cloud execution in this capability lane. Current actual capacity remains
UNMEASURED; a failed or unrun campaign remains refused.
