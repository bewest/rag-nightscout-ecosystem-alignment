# Bounded control/recovery archived-source measurement

Reproduced 2026-11-06 against committed application source
`8713395992e07b4dd2cde61ee972e9a15c8ada8c`. Each run uses a fresh full-source
archive and lockfile-matched private acceptance dependencies. Synthetic data only.

| Native gate | Positive | Authored control | Fresh restored positive |
|---|---:|---|---:|
| selected owner reader | 12 pass, 0 pending | 1 assertion fails: freshly tightened ceiling still admits three protected operations | 12 pass, 0 pending |
| persisted durable replay | 7 pass, 0 pending | 1 assertion fails: two stored identity kinds collapse to one projected row | 7 pass, 0 pending |

Owner runs1–2 used instrument `470354eae413c93513e7bb9adc01160cf7ae83ae`.
Remaining runs used `303470b5bad970f17a462c1fc9a1e8c9dfd3e27c`.
The original owner-control gate rejected Mocha's formatted-array assertion values;
its log and original native JSON report are retained unchanged apart from log
machine-path replacement. The latter instrument recognizes only the exact known
three-boolean rendering, rejects other counts/mixed values/extra tokens, and
validated the SAME captured report offline. No repeat owner-control database run
occurred. The initial gate classification was invalid; the native assertion is
accepted semantic evidence after this explicit offline reclassification.

Owner control removes only selected reader catalogue/ceiling intersection. It
retains signature, tenant and current-state checks, unsupported-shape refusals,
writer policy and unselected behavior. Replay control removes only id_kind from
the projection map key. The archived replay test adds an independent stored-row
count=2/distinct-kind count=2 oracle before the existing projected count/type
assertions. Storage identity keying is unchanged. Both controls exit1; fixture
startup failures and unrelated assertion symptoms are rejected.

Exact six generated containers and captured anonymous volume IDs are recorded
with absence checks. All were absent; volume baseline remained462. Older unknown
baseline fixtures were preserved. Runtime released22:09:12Z. Raw private run
artifacts remain under the owned alignment worktree's ignored externals/work.
Published logs replace only machine-local alignment prefixes. The artifact index
covers captured measurement artifacts; this explanatory file is separate.

These native gates measure dormant explicit selected readers and current-state
checkpoint/projection recovery. They do not activate the mode, prove selected
actual-client compatibility, establish performance, close management/provider/
listener/evaluator gaps, or complete M5/M6. No full/browser/corpus/prcheck run was
performed by this lane. Classifier source checks are instrument-only, not extra
application runtime evidence. Final lint:0errors24dynamic-filesystem warnings.
