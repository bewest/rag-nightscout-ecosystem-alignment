# M7 joined receipt gate

A cheap, read-only **recorded-evidence** checker. It runs no application, database,
Docker, browser, cloud job or test campaign, changes no queue state, and emits no
receipt. A passing check validates an independently selected expectation against
captured proof; it does not manufacture acceptance or infer runtime equivalence.
The current failed D5 UNIT campaign cannot pass it.

```bash
python3 tools/queue/gates/m7_joined_receipt.py \
  --expected /reviewed/m7-expectation.json \
  --receipt /captured/m7-receipt.json --evidence-root /captured \
  --scope acceptance
python3 -m unittest discover -s tools/queue/gates -p test_m7_joined_receipt.py -v
```

Exit 0 prints `PASS` with the exact verified scopes and `RECORDED_EVIDENCE_ONLY`.
Exit 1 prints a bounded `REFUSED M7_*` code. The files and their contents are never
printed. Artifact reads reject traversal/symlinks and duplicate JSON keys; at most
256 files, 16 MiB per file and 64 MiB total are read. Python bytecode writing is off.
An absent or oversized capture is refusal, not a reason to trim evidence to pass.

## Independent expectation and receipt

The coordinator maintains the expectation separately from the receipt. Queue gates
must pin that reviewed expectation, never derive it from the candidate receipt.
There is no production expectation or PASS receipt in this change. Unit fixtures
exist only in owned temporary directories with explicitly synthetic identities.

Expectation fields:

- `version: 1`, `kind: "m7-joined-expectation"`.
- `identity`: exact `pair: {core, deploy}`, `imageId: "sha256:..."`, and `instrument`
  content SHA-256. Source commits are full lowercase 40-character hashes.
- `artifacts`: reviewed relative-path → SHA-256 map from captured artifact manifests.
  Every referenced file must match both this independent pin and its receipt reference.
- `pending`: all eight tier names plus `corpus`, each `{count, reason}`. A known one
  pending is allowed only when explicitly pinned with a reason (the D5 UNIT exception was the absent external `VIEWS_CORPUS_DIR` moment-date corpus); zero is not a
  universal requirement. A different count refuses.
- `corpusCommand`: the actual enabled-corpus command ID in the worker result.
  `corpusSuites`: the full selected frozen-source inventory from the corpus runner.
  Missing, duplicate or extra selected suites refuse. The gate does not discover
  applicability or silently reduce this list.
- Nonempty `criteria` and `controls`: the coordinator's required native, pinned-client,
  clinical, OIDC, image/source, prcheck and semantic-control checklist. This is the
  policy boundary: eight tiers alone do not choose that checklist for an operator.

Receipt fields use the existing remote-seam vocabulary: `version: 1`,
`kind: "joined-acceptance"`, `status: "PASS"`, flat `pair`, `imageId`, `instrument`,
plus `claims`, the artifact references and required proofs below. `evidenceSha256`
is the hash of the referenced worker campaign result. These fields alone never
pass the gate. Diagnostic receipts are refused even if someone labels them PASS.

An artifact reference is exactly `{path, sha256}`. All paths are relative to the
explicit evidence root (default: the receipt's parent). Earlier committed evidence
can be referenced beneath an alignment-root evidence directory; do not use `..`
or symlinks. Raw private runner artifacts may stay private: the checker reads only
selected references and prints neither contents nor paths.

## Actual campaign fields, not new result truth

`campaign` references the worker's existing `result.json`:

- `scope == FROZEN_CORE_FUNCTIONAL_ACCEPTANCE_EXECUTION`, `status == passed`, empty
  `errors`, exact approved functional `source.coreCommit/deployCommit` (see compositional boundary below), verified owned Mongo cleanup
  and empty fixture/container-volume residuals.
- Every `unit`, `dom`, `dependency`, `core`, `harness`, `integration`, `stress` and
  `browser` command must exist with `status: passed` and numeric `returnCode: 0`.
  A top-level PASS cannot replace a missing or not-run command.
- `tierLogs` references each command's actual `stdout` path, resolved relative to
  the campaign artifact. The checker reads the real Mocha epilogue: one positive
  passing count, zero failing and the explicit expected pending count. Missing or
  ambiguous epilogues refuse rather than guessing.
- The configured `corpusCommand` must also have completed. `corpus` references the
  actual `scripts/test-multitenant.js --record` JSON: exact `suites`, `status: 0`,
  positive `result.passing`, zero `result.failing`, the declared `result.pending`,
  normal exit and empty `remaining` cleanup inventory.

If a future producer renames these fields, update/review its adapter explicitly.
Do not copy a successful counter from another run or make a new independent PASS
summary. Artifact pins select the reviewed captured bytes. A public projection may remove private argv/environment fields or rebase capture paths before immutable capture; retain raw/published hashes and the normalization description. The assessed status, return codes, counters, source identities and suite selections must remain verbatim. Redaction is not permission to synthesize a successful result.

Each extra criterion specification is `{attribution, assertions}`; its receipt
proof is `{attribution, artifact}`. Attribution must match exactly and includes a
required `core`, with optional exact `deploy`, `baseline`, `instrument`, `imageId`,
`credentialProfile`, and `diagnostics: ON|OFF`. Assertions are nonempty literal
JSON-pointer → expected-value pairs against the pinned original JSON artifact.
There is no expression language, command execution or inferred ancestry allowance.
Use source/provenance assertions alongside outcome assertions where the producer
provides them. For example, pin the OIDC `sourceCommit`, `complete` and all required
stage verdicts; pin both clinical source context and every required comparison.
Clinical baseline-pair and earlier OIDC evidence can retain their actual exact
attribution when the coordinator explicitly approves it. Never relabel old bytes
as the new HEAD or assume source equivalence from a branch name.

Controls require `baseline`, `broken`, `restored` specifications/proofs. Each binds
an original artifact and literal assertions. Baseline/restored must assert a green
outcome (`GREEN`, `PASS`, `passed` or exit 0); broken must assert red (`RED`, `FAIL`,
`failed` or positive exit code). Also select the actual semantic discriminator,
so a setup error does not stand in for a meaningful red. Changing a broken result
to green, dropping restoration, or omitting a required control refuses.

## Claims stay separate

Every receipt claims `acceptance`. `--scope` must be present in `claims`, and every
claim in the receipt is checked even when the caller selects acceptance. No
unchecked capacity claim can ride inside an accepted functional receipt.

| Scope | Required additional proof |
|---|---|
| `acceptance` | Campaign, corpus and selected criterion/control proofs; no future capacity requirement. |
| `pilot` | `pilot` artifact has 500/750/1,000 tenants at one coordinator-pinned fixed API replica profile (1, 2 or 4), actual remote-pilot cadence and measurements. It establishes neither stable capacity-profile 1k nor 3k. |
| `capacity-milestone` | Claimed capacity-profile tenant/API target PASS; every independently required comparison measured, with honest FAIL comparisons retained. No mandatory 10k stretch PASS. |
| `api-scaling` | Includes `capacity-milestone`; requires measured 1/2/4 API comparisons at the same target tenant count/profile/host. One API need not PASS 3k when four APIs do. This records comparisons, not a claim of linear speedup. |
| `full-ladder` | Optional stricter existing `campaign_check`: all 1k/3k/5k/10k × API 1/2/4 cells PASS. This does not redefine the adopted 3k milestone. |
| `scaling` | Includes `api-scaling`; all five component contracts and explicit binding inventory below. API-only data cannot close this scope. |

For a pilot claim the expectation must explicitly set `pilotReplicas: 1|2|4`; all three levels must use that same profile. This receipt predicate uses the existing per-cell fields; it does not silently change the older adapter `pilot_check`, which at this source accepts only replica profile 1. The controller must use its matching selected instrument. A fixed two-API pilot is not an API-scaling comparison.

`capacityMilestone` in the expectation is exactly
`{tenants, replicas, profile: "capacity", hostIdentity, comparisons}`;
`comparisons` is a list of `{tenants, replicas}` including the target. The receipt's
`milestoneCells` is a list of pinned original per-cell `summary.json` references.
No aggregate PASS is invented: current `campaign.py` omits failed cells from its
master, while `adapter.py` writes their summaries before raising. Use those actual
retained files for FAIL comparisons. Duplicate/missing/wrong-source cells refuse.

Cells retain the producer's `verdict == PASS iff all(correctness)` assessment and
oracle/uncertainty consistency. Claimed targets must PASS. All selected cells need
complete actual numeric HTTP and role observations, positive sample counts, and
observed windows covering the existing profile cadence. The expectation must pin `capacityInventories["<profile>:<replicas>"]` as `{httpShapes, windows}`. `httpShapes` is the exact seven names from the selected workload. `windows` contains `idle-disabled`, `idle`, `load`; each maps logical `api`, `realtime`, `evaluator`, `postgres`, `vault` server (and optional distinct `vault-agent` / `other`) to the actual Compose service names selected for that profile/window. API inventory length matches the replica count. Actual role keys and shape keys must match exactly; names are not guessed by the checker. Co-located roles may explicitly share a container observation, which does not create separate per-role CPU/RSS figures.

Every selected serving role requires finite nonnegative snapshot CPU/cgroup memory fields, `counterReset: false`, and its actual `processRssKiBAfter` Docker `top -eo pid,comm,rss` table with numeric RSS KiB rows. Idle/load additionally require positive sample count and finite sampled CPU/memory observations. The 60-second sampler-disabled control requires its actual snapshot fields, not invented sampler values. RSS is not replaced with cgroup memory or labelled as JS heap. Already-exited load generators belong to their separate resource observations, not fabricated serving-role snapshots. The gate reuses existing
profile/ladder contracts without altering them or inventing latency thresholds.
Stable capacity-profile 1k, adopted 3k, 5k observations and 10k stretch remain
explicit targets, not aliases for a small functional diagnostic.

For broad scaling, expectation `scaling` has exactly `api`, `realtime`, `evaluator`,
`postgres`, `vault-agent`. Each value contains a source-specific `proof` specification
and at least two `observations`: `{configuration, samples, metrics}`. Configuration
and sample values are JSON pointers into the actual pinned measurement artifact;
metrics maps numeric observation pointers to explicit units. Configurations must
be distinct, samples positive, metrics finite numeric observations. A static
`scales: true` or `measurements.complete: true` is insufficient. The coordinator
selects the concrete workload/resource/semantic assertions; the gate cannot infer
whether a scaling curve or a discovered binding is acceptable.

`bindings` references `{pair, complete: true, entries}`. Entries may be explicitly
empty; findings carry `component`, `file`, positive `line`, and `finding`.
Base capacity uses the actual Vault server and does not silently activate an Agent overlay. Broad `vault-agent` scaling additionally pins `agentRoles` in that component specification and a `roles` JSON pointer in each observation. Its sample and metric selectors must address those actual observed Agent roles, disjoint from the pinned Vault server names. A server-only record cannot be relabelled Agent evidence.

Do not erase an actual binding to obtain an empty inventory.

## Coordinator queue wiring

After actual proof exists, root can add source-paired recorded-evidence gates to
endpoint/API, registry/live-add, D6, socket-cap, sharding and auth-cost items using
one shared acceptance record and their complete checklist. Preserve historical
leaf evidence separately. Wire baseline milestones to `capacity-milestone`,
API comparison to `api-scaling`, and broad scale to `scaling`; strict full-ladder
is optional, not the adopted 3k prerequisite. Retired contrast stays retired.

Each exact command/cwd needs its `gate-controls.yaml` entry: missing required
suite/control, diagnostic-as-full, wrong identity, missing API comparison or
component observation must go red; restored fixture goes green. The included
focused suite runs these in owned temporary records, including a checker-source
ablation that falsely admits a missing control and makes its refusal oracle red.
No queue/release/decision file is changed by this capability.

## Current profile selection and functional campaign composition

Capacity/pilot expectations now pin the producer's complete actual
`profileSelection` object, including its canonical `sha256`, selected settings
schema/hash/source blobs, diagnostics mode/interval/environment and default
registry topology. It must name the primary exact core. Every comparison cell,
and pilot/full-ladder aggregate, must equal that pin. Even with identical
source/image/instrument, diagnostics ON versus OFF, changed selected settings or
changed realtime/evaluator topology are different profiles. API replica count
is intentionally outside this object. Deliberate ON/OFF overhead experiments
need distinct named profiles; they cannot silently become API-scaling cells.
Each selected cell also needs actual `settingsFingerprintObservation` with
positive observations, zero invalid/mismatch and PASS. Historical summaries
without observations cannot acquire this proof by inserting inferred defaults.
The source-owned producer contract and capabilities describe the exact fields
in [PROFILE-SEAM.md](../../mt-bench/m7-joined/PROFILE-SEAM.md).

Optional expectation `functionalCampaignPair: {core, deploy}` defaults to the
primary `identity.pair`. Its core MUST exactly equal the primary core; its deploy
must match the exact deployment metadata captured by the approved core-only
worker. This is specific to `FROZEN_CORE_FUNCTIONAL_ACCEPTANCE_EXECUTION`:
original worker `tools/perf-cloud/core-acceptance.py` at deploy instrument
`3d8ca353f973433021ae2086cd643d03da5fb3a4`, blob
`d39a96a7412e246e77b7619565965e665fce0e81`, runs commands in its pinned core
checkout, installs/bundles core and runs core tiers/corpus. Its deployment pin is
authorization/metadata, not an executed binding. This is a read-derived scope
verification of that exact worker, not permission to substitute an equivalent
core or rewrite its captured source fields. A later worker that executes the
deployment binding needs a new reviewed scope contract.

The primary identity remains the exact final paired image. Required paired-image
and native binding criteria stay separately pinned to their actual final
source/image/instrument attribution in the coordinator's `criteria` policy.
The coordinator must retain those reviewed criteria: accepting a core-only
campaign with an explicitly approved earlier deployment metadata pin does not
prove the final binding. Wrong/missing approval refuses; any different core
refuses; a binding proof attributed to the earlier metadata deployment refuses
when the final deployment is required. No receipt or source identity is relabelled.

Capacity/pilot cells now require coordinator-pinned `evaluatorProgressArtifacts`
keyed `profile:tenants:replicas`, with exactly idle/load/recovery gzip references.
The summary's `evaluatorProgress` fields must match independently recomputed
counters, coverage, identity, generation and hidden-error checks from complete rows.
The policies are fixed in profile-selection version3; previous cycle-only observation
is insufficient. Recovery additionally requires changed runtimes and successful
owned acquisitions, separately from time-only idle/load progression.

Only these explicit progress artifact types are gzip-decoded. Streaming decoding
refuses more than16MiB per artifact or64MiB total decoded progress per invocation,
in addition to existing compressed/general evidence limits. The optional large
ladder can therefore remain UNMEASURED when its complete proof exceeds the budget;
there is no raised cap, omitted foreign evidence or inferred PASS. Full functional
acceptance alone still does not require future capacity proof. Root owns expected
artifact/source policies and queue wiring; these helpers never write a receipt.

Current cells require explicit idle-safety-v1 plus strict load/recovery artifact v2.
Every compact row retains typed dueAt/dueReason, including finite fractions;
strict successful-work and changed-runtime recovery assertions are unchanged. Current receipts
refuse downgrade to legacy unknown-due artifacts. The shared artifact decoder
separately supports historical v1 with its exact original policy/columns, leaving
due metadata absent/UNKNOWN instead of manufacturing null. Historical proof is
never upgraded or relabelled. Existing source/image/instrument/profile pins and
streaming16MiB/64MiB decoded limits continue to apply.


Current `profileSelection` version3 also pins `evaluatorIdleSafety`. The required
idle artifact is `evaluator-idle-safety-v1`: complete typed clinical job metadata,
actual read UTC/monotonic brackets and helper observations must independently
recompute opportunity-aware sampled idle safety. Quiet results explicitly say
TIME_NOT_EXERCISED, zero completions and `timeWitness:false`; source/runtime/
ownership/errors, foreign work, new acquisition demand, missing jobs/timestamps
and any earlier observed due without later time completion refuse. Current
explicit null plus complete no-pending state means NO_TIMER_DECLARED; historical
missing/unknown is never converted to null. Old v1/v2 decoders remain historical
strict proofs and cannot satisfy the new current idle artifact requirement.

Capacity/pilot evidence additionally needs `nativeEvaluatorTimeWitness` in the
independent expectation, exactly `{artifact, attribution, tenants, services,
proofPointer}`. `attribution` pins `{core, deploy, imageId, instrument}`. The artifact
is the actual native-bounded-evaluator-due-listener-qualification wrapper, whose
source/binding/image/instrument fields must match those pins; `proofPointer` selects
its embedded strict v2 successful idle-TIME proof. The unchanged checker recomputes
positive time progression for every native owner. An idle-safety PASS, a future
timer or a quiet native capture cannot substitute. Any earlier source exception
requires an explicit reviewed attribution pin; equivalence is never inferred.
This support criterion does not turn quiet-baseline metrics into active-alarm
capacity and does not add capacity requirements to functional acceptance alone.
