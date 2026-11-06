# Cumulative REST head: bounded historical compatibility refresh

Contributor-facing measurement, 2026-11-05. The [aggregate](aggregate.json) records
fresh repeated runs of the released source, current development and the new local
REST candidate. Each uses the same bounded synthetic write matrix. This is a new
capture; the [earlier capture](../compat-refresh-2026-11-05/README.md) is retained.

## Source and runtime binding

The [expected configuration](expected.json) binds the audit to full source hashes
and checked dependency manifests. Candidate `d4570e585d0e12e46386ed26772790b269b2b736`
is local cumulative work. It is not the published PR head. Baselines are released
v15.0.9 `c6a0d8ed65637bc90d3090e6e7a0f752041c57fd` and official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563`. All three were archived into private
scratch trees and run twice. Release/development repeats were captured earlier in
this same campaign and retained when the candidate advanced from `d1d8c520` to
`d4570e58`; the final candidate and its controls were measured anew. No endpoint
input is borrowed from the previous campaign. The source delta between those two
candidates contains only `tests/write-intent.d-event.test.js` and
`lib/storage/PORT-CONTRACT.md`. The precursor pins remain local without relabeling.
Application library source was clean in all endpoint runs.

Runtime is Node 22.23.4 and MongoDB 7.0.43, with a dedicated container, random
loopback port and `nofile=65536:65536`. Each matrix process gets a random test
database and drops it after completion. Driver versions were read from installed
package manifests and checked against each source lockfile before launch:
v15.0.9 uses 5.9.2; development and candidate use **7.7.0**. The earlier report's
7.6.0 wording described a dependency range rather than a verified installed
version. This capture does not retroactively assign a driver version to old pins.

The local environment sidecar contains hashes of each source lockfile and installed
MongoDB package manifest. Its initial hashed snapshot was taken before the final candidate
launched, with this campaign’s release/development captures already underway;
those driver versions were separately checked before their launches. Its final
snapshot was taken after all runs and controls. The auditor requires both snapshots to match
[expected.json](expected.json). This checks the declared dependency provenance,
not the complete dependency tree or a runtime trace of every module load.

## Instrument, prediction and limits

The matrix and its scratch adaptations are unchanged from the
[earlier method](../compat-refresh-2026-11-05/README.md#sources-and-instrument):
`--batch --no-idf --no-idfmt`, all ordinary collections and four write paths,
ordinary cross-path cells, Temporary Target cells and batch forms. Current
sources set `WRITE_IDENTIFIER_INDEX=off`; release settings remain default.
The database prefix contains `test`; the narrow database-token normalization
and the old-release missing-`storage-reads` guard are retained. The six old-release
`idread-fail` cells remain incomparable. Cache/wire differences remain separate
from semantic comparisons. No old captures were rewritten.

Before execution, the prediction was zero semantic differences between development
and the new candidate, stable repeated endpoints, and rejection of the authored
breaks. Release differences were to be measured rather than inferred from prior
heads. Any current-source mismatch stops automatic acceptance. The result's
`passed` covers only this fresh development/candidate equality, repeated endpoints,
source/runtime/settings/dependency bindings and controls. It does not approve
historical full-corpus residuals or establish complete backwards compatibility.

Historical classification and residuals remain descriptive diagnostics. The old
full-corpus capture has different fixture context: omitting identity families
shifts synthetic timestamps relative to API v1's default date window; one old
placeholder fixture retains a different identifier form; and the test-prefix
adaptation changes truncated error text. The earlier record explains these
boundaries. No new expected-change allowance was added. Existing release decisions,
backfix entries and client-shape catalogue remain the interpretation sources.
Client applications, omitted identifier/quirk families, index-on behavior,
PostgreSQL and multitenant execution are outside this matrix. The separately
measured nonresident profile branch is not an endpoint here.

## Controls and reproduction

The new candidate's actual API v3 insert call was removed in a fourth private
archive. Liveness stayed valid and the reply remained HTTP 201, while persisted
state became `none`. Restoring the original source restored the good create
result. Control source hashes are checked against the new candidate, so old
controls cannot be relabeled for this capture.

The comparator's unexpected-field, error-reply and missing-cell controls remain.
CLI negative controls corrupt a candidate repeat, give both candidate repeats
the same wrong head, and alter the environment sidecar. Their expected result is
exit 1 with a specific failure; the unmodified capture must exit 0. The original
no-config audit is also rerun and must produce an aggregate byte-identical to
its retained result. The reproduced CLI outcomes are retained in
[audit-controls.json](audit-controls.json).

With the new pins and environment sidecar in a private directory:

```bash
python3 tools/qc/compat/bounded_refresh.py --pins "$PINS" \
  --expected-config reports/compat-rest-next-2026-11-05/expected.json \
  --out "$AGGREGATE" --detail "$LOCAL_DETAIL"
```

The unchanged matrix invocation and source-ablation recipe are in the earlier
method record. `WC_MONGO` remains an environment value; source snapshots and full
pins stay local. The public aggregate contains counts, classification groups,
source/dependency metadata and hashes, without document bodies or database URLs.
