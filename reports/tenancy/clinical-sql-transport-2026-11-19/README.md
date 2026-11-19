# Clinical SQL observation transport

**Fixed on a local helper branch; live timing remains UNMEASURED.** The frozen
base is `b0f327a8ce8c554ea06db5b4010dbcb4e96ba3e6`. This lane changed no
application, native policy or entered helper. The parent integration owner
selects the next joined candidate and transfers empty custody to its campaign
owner; this result authorizes no old-pair live retry.

The generated probe now calls `clinical-sql`, a targeted PostgreSQL observation
path. The original `sql` command and all campaign censuses are unchanged. Each
clinical child still performs full instrument, render, inventory, packet and
configuration validation. Its query brackets the selected namespace, PostgreSQL
workload, Pod and running container with namespace/owner/UID, controller, source
image/command, image ID, process incarnation and readiness checks. An identity
change before SQL prevents execution; a change after SQL prevents any response
being emitted. These checks use the full campaign baseline rather than selecting
a replacement Pod. They do not re-read unrelated UI/setup/native-load objects.

The exact clinical query bytes still run through the original
`BEGIN READ ONLY … ROLLBACK` wrapper. The full clinical projection and strict
stored/native/frame/BG-now oracle are unchanged. Actual database, PostgreSQL
system/timeline, native source/generation and restore fences stay in that SELECT
and oracle. The child timeout remains 60,000 ms and the clinical witness deadline
remains 120,000 ms. A new internal observation bracket can only shorten the
original work cutoff. No timeout or missing observation earns clinical credit.

## Reproduced observations

The retained case `kcap-source49f-native-n8-08` contains a SQL child TIMEOUT after
60,006.091630 ms, with zero stdout/stderr bytes and no reported child code. Its
failure receipt SHA256 is
`0c1d51bf08f98156791314725bf434086d19c2800432765bc49c67f5f9ccee5e`.
The exact stage responsible for that timeout remains UNMEASURED. In particular,
the following local measurements do not identify hashing as its cause.

Read-only replay from an archive of the frozen source measured:

| Local operation | Measured wall cost |
|---|---|
| Python adapter import | 0.054243 seconds |
| Instrument hash, three repetitions | 0.018393 / 0.021488 / 0.025361 seconds |
| Full historical input load/validation, three repetitions | 0.090362 / 0.028348 / 0.035086 seconds |

The instrument covered 247 files and 2,721,253 bytes and matched the retained run
exactly. Historical replay used the recorded initial observation time solely to
read/validate the expired capture; it executed no API or SQL call. These fast
input/source checks remain in each clinical child.

The actual native synthetic control fixture measured the following read counts
and serialized JSON payload sizes. These are in-process synthetic API/SQL
replies, not network or database measurements:

| Observer path | API GETs | API JSON bytes | SQL execs | SQL request / response bytes | Local wall / Python CPU seconds |
|---|---:|---:|---:|---:|---:|
| Original full census | 40 | 65,060 | 1 | 56 / 19 | 0.007759 / 0.007759 |
| Targeted clinical bracket | 6 | 3,710 | 1 | 56 / 19 | 0.000362 / 0.000363 |

The six GETs read namespace, selected PostgreSQL workload and exact baseline Pod
before and after SQL. The retained real campaign had 50 observed objects and
13 Pods. **Read-derived:** the original two full censuses require at least 106
API reads plus SQL, before any extra native exact-object reads. That explains
unnecessary per-query work structurally; it does not establish which call spent
the retained timeout or predict a live latency improvement. No quiet-host or
capacity comparison was made.

## Controls, validation and limits

Meaningful wrong namespace/label, workload/Pod/controller UID, container ID,
restart count, actual image, source image and readiness controls fail before and
after SQL and restore green. Namespace-UID and container-identity branch
ablations make their refusal criteria red, then restore green. Terminating
resources, expired work, overlong/non-SELECT input and bytes arriving beyond the
selected observation window refuse. An unrelated UI replacement is outside the
clinical bracket but still fails the unchanged full campaign census.

The unchanged actual clinical oracle rejects synthetic wrong database, system,
timeline, native generation, restore target, foreign tenant, stale completion,
clinical mean, frame and stored row, then restores green. The generated real
probe control reaches the same raw SQL/stored/clinical/client/accounting oracle
through the new command. It asserts the unchanged 60-second child timeout;
generated-source controls assert the unchanged 120-second monotonic clinical
check. No clinical projection was compacted or synthesized as observed evidence.

Affected Python suites ran 54 tests: 53 passed and one optional qualified-render
test was skipped. The native-observation Node suite passed 28 tests and skipped
one optional source-selection test. The dedicated native clinical and claims
control programs passed. `make queue-check` and `git diff --check` passed.
Application full/browser acceptance was skipped: this lane changed only the
observation helper and requires a future joined live measurement by its owner.

Retained evidence identifier:
`kubernetes-capacity-20261118/native-join/clinical-sql-transport`. It contains the
frozen-source input-cost replay, exact helper instrument, synthetic observer
cost and all test logs. Helper instrument SHA256:
`3679cc2446a962a03b97c9e36ff022f99c704110be9952ecc6417fca26a66b8b`
(249 files). Lane detail:
`/mnt/data/nightscout-workspace/artifacts/handoffs/HANDOFF-clinical-sql-transport-2026-11-19.md`
(local).

No Kubernetes, provider, Docker mutation, publication, Git push, peer change or
source-status promotion occurred. The original timeout and clinical UNMEASURED
outcome remain unchanged. Live API latency, SQL execution time, correctness on
the next joined candidate and final capacity remain with the campaign owner.
