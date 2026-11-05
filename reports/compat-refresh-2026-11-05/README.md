# Bounded historical write compatibility refresh

Contributor-facing measurement, 2026-11-05. This refresh compares a common synthetic
write corpus on three fresh single-tenant MongoDB endpoints. It does not compose
historical MongoDB behavior with a separate PostgreSQL or multitenant comparison.
The machine-readable [aggregate](aggregate.json) is the result record.

## Sources and instrument

| Endpoint | Source commit |
| --- | --- |
| Released v15.0.9 | `c6a0d8ed65637bc90d3090e6e7a0f752041c57fd` |
| Current official/dev | `4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| PR #8898, single-tenant path | `ded254b9acf5a94e3a4fd99c85b23e1413fa08b6` |

Source trees were archived into private scratch checkouts with their original Git
heads. The application source was clean for every endpoint run. Dependencies were
read-only links to matching local installs: MongoDB driver 5.9.2 for the release,
and 7.6.0 for current development and the candidate. No browser assets were built
or borrowed for this server-only matrix. Runtime: Node 22.23.4, MongoDB 7.0.43;
an owned container exposed a random loopback port, with a separate random test
database for each run. The harness drops its database after completion.

The instrument is [write-contract-matrix.js](../../tools/qc/write-contract-matrix.js)
at alignment `2294a8944a0eac8e72da866cb70f0580fc7b0c18`, invoked with
`--batch --no-idf --no-idfmt`. All six ordinary collections, all four paths
(API v1, API v3, websocket, in-process), ordinary cross-path cells, Temporary
Target cells and batch forms remain. Settings, identifier-resend and identifier-format
families are excluded. `WRITE_IDENTIFIER_INDEX=off` on development and candidate;
release settings are default. This is not index-on evidence.

Two local harness adaptations are recorded: the established old-release
`storage-reads` guard (that module is absent on v15.0.9), and database prefix
`wcm_test_` instead of `wcm_`. The latter exposed an instrumentation issue: the
existing error anonymizer recognized only the old prefix before truncating replies.
The auditor removes only the exact random `wcm_test_<8 hex>` token from cell text
before comparing repeats; every other error field remains measured. It does not
restore the text already truncated by that anonymizer. Six old-release websocket
`idread-fail` cells are incomparable because their injection cannot fire on that
source, and are excluded only from release comparisons.

## Predictions, measurements and controls

Before execution, the recorded prediction was that earlier classified release
changes would remain, with no unexplained current development-to-candidate storage
or reply changes. Any new current-source difference required investigation rather
than a broad classification allowance. Cache and wire are counted separately from
semantic equality, following the existing matrix protocol.

The reproduced observations and control outcomes are in the aggregate. Each tree
was run twice. Development and candidate match on the fresh bounded corpus.
Release-to-candidate changes use the same changed-cell set and the same per-cell
mechanical groups as the selected cells in the earlier full-corpus comparison.
This is descriptive corroboration; the older capture is not a fresh repeat.

The authored source control removed the actual API v3 `storage.insertOne` call
from `lib/storage/write-intent.js` in a fourth private archive. A treatment create
still answered HTTP 201 and liveness remained valid, but stored state was `none`
instead of `n=1 OID`. The auditor rejects that result. Restoring the original file
restored semantic equality with the candidate's create cell. Separate comparator
controls add an unexpected field, change a successful reply to 500, and remove a
cell; each is rejected. A deliberately corrupted candidate repeat also made the
command exit 1 with `pr8898: nonrepeatable semantic cells`. Giving both candidate
repeat pins the same wrong head also exits 1, reporting a wrong endpoint head for
each run. The auditor binds this dated capture to its exact source/runtime/settings;
driver versions are read-installed metadata because the original pins do not emit
a driver-version field. These controls establish detection of the stated breaks,
not completeness against every possible regression.

## Historical attribution boundary

The previous [refresh](../../tools/qc/results/write-contract-matrix/compat-16.0.0-refresh-2026-11-01/analysis.json)
ran the full corpus. It cannot be projected as an exact expected-value pin for this
shorter corpus: the aggregate retains the residual counts rather than calling
them approved release differences. In particular, the harness advances synthetic
time by 61 seconds per cell and seeds the batch-taken records seven days earlier;
omitting families changes their position relative to the API v1 default date
window (`lib/server/query.js:140`). This is a read-derived explanation for the
observed read-count residuals, not a separately controlled timing experiment.
One released-treatment placeholder fixture also retains a different stored identifier
form when earlier identity fixtures are omitted. The full-corpus context was not
rerun to isolate that dependency. Random-database error truncation is another
explicit residual source. No new expected-change allowance was added.

The existing [group definitions](../../releases/cgm-remote-monitor-16.0.0/compat/groups.yaml)
and [release decisions](../../releases/cgm-remote-monitor-16.0.0/decisions.md) remain
the interpretation sources: identifier-first duplicate avoidance; ID-Q6 format
handling; socket batch fixes; BF-170 client `_id` refusal; BF-194 Temporary Target
units; and reply/event/stamp changes. No new group or `Defect` verdict was introduced
by the mechanical classification. These group names do not themselves authorize
an unexpected changed field.

The [client-shape catalogue](../../tools/qc/results/write-contract-matrix/compat-16.0.0/client-shapes.json)
is read-derived client-code evidence. This run exercises generic transport shapes,
including v1 edits and replies, but does not replay client applications, refresh
client versions, or test the omitted identity/quirk families. It does not establish
universal backwards compatibility or old-release-to-multitenant transitivity.

## Reproduce and audit

Prepare archived, dependency-complete source directories at the three commits and
an owned MongoDB 7.0.43 service. Set `WC_MONGO` through the environment. Prepare a
scratch copy of the matrix with the two adaptations above; use the old-release
guard only for v15.0.9. For each endpoint run twice, writing
`v1509-run{1,2}.json`, `dev-run{1,2}.json`, and `pr8898-run{1,2}.json`:

```bash
WC_WORKTREE="$SOURCE" node "$HARNESS" --batch --no-idf --no-idfmt --out "$PIN"
```

Set `WRITE_IDENTIFIER_INDEX=off` for development and candidate. For the source
control and restored control use `--only treatments --paths v3 --forms create
--no-cross --no-idf --no-idfmt --no-tt`, saving `control-no-write.json` and
`control-restored.json`. Then run:

```bash
python3 tools/qc/compat/bounded_refresh.py --pins "$PINS" \
  --out "$AGGREGATE" --detail "$LOCAL_DETAIL"
```

The auditor fails on incomplete corpus, nonrepeatable semantic cells, dirty source,
heads other than the dated endpoint pins, unexpected Node/MongoDB or recorded write
settings, unequal endpoint cell sets, invalid liveness, any fresh development/candidate semantic difference,
or an ineffective control. Historical projection residuals stay diagnostic and are
outside its explicit pass scope. Full pins and diagnostics remain local; the public
aggregate carries their hashes without document bodies or database addresses.
