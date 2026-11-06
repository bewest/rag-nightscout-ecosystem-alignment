# M4 actual-client lab — 2026-11-06

*Contributor-facing snapshot, 2026-11-06, archived CRM `35903069b46974cfbaddd8dce00c994fb2562bc3`. Current item state lives in `queue/work-queue.yaml`; subsequent acceptance must use a new capture.*

**Reproduced measurements, bounded scope.** This capture executes installed client programs;
it is separate from R40/R41 source-pattern replay. The default M4 compatibility gate remains
red. No application fix, milestone promotion, publication or release is claimed.

## Anchors and runtime

Alignment base: `88902eba2532c42bf83a91a8104f9ea64da2ca18`. Every server in the recorded
pairs was booted from an archive of CRM `35903069b46974cfbaddd8dce00c994fb2562bc3`.
The archive gate checked its lockfile against the private dependency source and passed its
selected commit explicitly to the lab. The private CRM worktree remained clean.

| Program actually executed | Package version | Checkout commit |
|---|---|---|
| cgmsim-lib | 0.10.3 | `c09f9c039007a80a431baec6dbf852c52e3669db` |
| oref0 | 0.7.1 | `d219baf9559d62a8bb0bd42014192a2d7c0839ef` |
| nightscout-connect | 0.1.1 | `04102f9d260f0d21f6b6ff66d4afe27680bef37c` |

The connector was **not** the workspace lock's `b394411a` or CRM's dependency version 0.1.0.
Server Node: v22.23.4; client container Node: v22.23.3 (printed in the cgmsim process logs);
PostgreSQL 16.15, MongoDB 8.0.34, Vault 2.2.1. Image content identities and capture hashes
are in the summary capsule. Two explicit preview tenants use direct-alias Host resolution,
with default access denied; the single-site Mongo baseline also denies anonymous access.
All data and identities are synthetic. No vendor account was contacted.

## Results

Counts are per capture and are not additive. A passing check count does not override a
classification failure. Stored documents came from independent MongoDB/PostgreSQL readers;
HTTP records came from the recording proxy. Generated primary keys and top-level server
clock stamps were separated from value comparison. Other nested values were retained.

| Capture | Reproduced result | Meaning |
|---|---|---|
| verified-build default and final restoration | 82/82 checks each; 19 cells per stack; three unexplained differences; exit 1 | actual pinned-source cgmsim and oref0, with original assertion behavior restored; compatibility gate not met |
| verified-build connector | 60/60 checks; two Share cells per stack; zero differences or missing cells; exit 0 | fixed-data upload/restart scope passed; preview-source observation passed separately |


The cgmsim source build is verified separately from its package label. The gate archives the
selected source, compiles it with locked TypeScript 4.9.5 and compares all 94 emitted runtime
JavaScript files before starting any fixture. The shared installed build failed that check
on `carbs.js` and `utils.js`; the separate clean worktree matched all 94 files. The stale shared
artifacts were left untouched. Earlier installed-artifact captures are retained as historical
measurements and are **not pinned-source cgmsim acceptance**.

The stale `utils.js` omitted the logging transport targets present in the pinned source.
Those historical processes reported `end() took too long (10s)` and exit 1. The clean pinned
build's lifecycle probe and its measured client operations exited 0. No Pino defect is assigned
to the pinned source from the stale-artifact observation. Source/dependency versions were not
changed to obtain that result.

The profile script and cgmsim synthetic driver used a fixed input clock, without editing the
installed client source. The oref0 command aliases came from its own package `bin` declarations
and were installed as symlinks only in the disposable fixture directory. This measures payload
and storage behavior, not scheduler timing.

## Differences and disposition

Every difference is retained in the classifier output. `groups.yaml` has no acceptance
exceptions: none of these findings has been waived or silently normalized. The assessments
below use the compatibility vocabulary; they are not maintainer decisions or approved fixes.

| Cell/mechanism | Reproduced difference | Assessment and basis |
|---|---|---|
| entry identity migration | Mongo retained a client identifier; preview omitted it from the corresponding stored logical record | **Defect candidate.** Observed value loss. Read-derived mechanism: single-site `lib/server/env.js:112` defaults `uuidHandling` true; preview `lib/server/tenant-app/environment.js:60` builds only settings/extendedSettings. `lib/storage/write-intent.js:1047` migrates the incoming identity only when that flag is set. No application repair applied. |
| oref0 header-mode latest-treatment lookup | Mongo 200 with one item and client exit 0; preview 500 and client exit 5 | **Defect candidate.** The actual client lookup is not compatible. Read-derived mechanism confirmed independently through the archived compiler: its native regular-expression serialization falls outside the PostgreSQL literal/time-helper grammar (`lib/storage/postgres-filter.js:120`). The equivalent literal pattern compiles; the emitted escaped form throws `UnsupportedQueryError: PostgreSQL entries read: unsupported regular expression outside the literal/time-helper subset`. No client request was rewritten. |
| oref0 token-mode malformed lookup | both stacks refuse with 401; baseline has description/message/status keys, preview has error | **No value change, reply-schema difference.** Access refusal is preserved and stored values match. This is an assessment, not an accepted compatibility exception. |

The token-mode lookup embeds its query in the report argument before the pinned `ns-get`
appends authentication. Its baseline refusal is a client property, not a preview regression.
The packet calls for measuring this malformed lookup rather than assuming HTTP 200.
Malformed-batch observations ran with validation at its default off setting; reject-mode
per-item refusal parity remains UNMEASURED.

## Actual connector scope

The connector ran unchanged against an M4-only fixed synthetic Share upstream. Each stack
stored exactly 240 mapped readings. Restart resent a newest subset, stored no duplicate,
preserved logical values and kept srvModified monotonic by stored identity. One poll was
selected; incremental new-reading polling remains UNMEASURED. The upstream holds a fixed
20-hour series; its invariant/range controls are covered by pure tests. The shared journey
fake upstream was left unchanged after source review reproduced changing historical values
from its moving integration window.

For source mode, the preview held three synthetic A entries and an empty single-site sink
received exactly those logical rows. Actual exchange returned 200 with the expected fields;
actual Bearer read and sink POST returned 200. B remained unchanged. This is a **preview
source to single-site sink observation**, not a fabricated baseline-as-source differential.
Without a token, verifyauth answered 401 and a subjects GET answered 405; onboarding was
blocked at the observed steps. Subject creation by POST was not demonstrated.

## Refusal and instrumentation controls

The verified-build default and connector captures exercised actual cgmsim/oref0 credential carriers. A's secret
or subject token at B refused reads/writes with 401; revocation refused the next read/write
with 401 and restoration read 200; unknown aliases returned 404. Every compared domain's
stored values on A, B and baseline remained identical across refused operations.

Absent-credential oref0 reads returned 401. Its missing-secret upload refused locally with
exit 1 and no HTTP request. Separate no-carrier POST protocol probes returned 401 on both
stacks; these probes are not actual-client upload execution. cgmsim hashes an empty secret,
so that is not an absent-carrier check. Oref0's revoked upload returned HTTP 401 and process
exit 0 because its curl invocation lacks `--fail`.

| Ablation | Reproduced red symptom | Restoration boundary |
|---|---|---|
| hosts, oref0 subset | 12 ordinary upload assertions failed; each client had no proxy request and exit 2; 12 separate resolution-symptom checks passed | default restored run reached both stacks; this is not a cgmsim/connector hosts ablation |
| wrong oracle, registered default clients | eight expected stored-value assertions failed with zero rows from B; HTTP still reached A | same default fixture assertions restored; unrelated compatibility findings persist |
| planted reply, oref0 subset | first ordinary entry reply label changed; classifier reports one additional unexplained cell | planted cell absent after restoration; original three differences persist |

The restored default run recorded **82 checks passing**, 19 cells per stack,
and the same three unexplained differences. Its exit remains 1. These controls prove their
specific checks notice the break; they do not establish a green default gate or queue-vacuity
acceptance while the positive gate is red. Every recorded run after the first audit-string
correction verified its owned containers absent and found no new volumes. The first run's
false absence flags came from a case-sensitive error-string check; independent exact-name
inspection confirmed those containers absent. No foreign resource was removed.


## Preparation and provenance failures retained

Earlier captures remain local and failed: wrong baseline cwd prevented translation loading;
an anonymous readiness probe could not succeed under denied access; the cgmsim driver used
a nonexistent download property; oref0 installed command aliases were absent; the recorder
did not decode a compressed connector reply; installed cgmsim generated artifacts did not match the pinned source. Each was recorded before a harness-only repair.
No application/client source or dependency version was changed to bypass a measured failure.

## Limits and next work

M4 remains open and its default gate is not met. Resolve the two candidate behavior defects
and decide the refusal-body compatibility contract before rerunning the default gate.
The main checkout/index and paused staged snapshot were preserved; the deliverable is an
isolated local branch. Root coordination allocates an integration-record R number after
combining B4a records; this standalone dated report does not claim one in advance.

Connector-specific cross-tenant/revocation negatives, baseline-as-source differential,
non-entry source collections, incremental polling, reject-mode malformed batches, mobile
binaries, v3 uploader binaries, socket forwarding/pattern replay, TLS/proxies, outage soak,
capacity and latency remain UNMEASURED. No D23 forwarder was built. No old-release
transitivity or general "no coordinated app upgrade" claim is made. Full/browser/corpus
acceptance belongs to B5 and was not rerun by this lane.

The [summary capsule](summary.json) retains whitelisted results and hashes of the local raw
captures/instrument snapshots. [Restored classification](restored-classified.json) retains every
difference. Earlier record files are unchanged. Pure harness checks, `make queue-validate`,
`make queue`, `make queue-check` and `make docs-links` were run on the isolated branch;
see the local handoff for exact command outputs and publication instructions.

Local continuation: `externals/work/HANDOFF-codex-m4-20261106.md` (untracked). The source
packet is [the M4 dispatch](../../../docs/30-design/tenancy/m4-client-binary-lab-packet-2026-11-06.md).
The lab manual is [the runner README](../../../tools/lab/m4-client-binaries/README.md).
