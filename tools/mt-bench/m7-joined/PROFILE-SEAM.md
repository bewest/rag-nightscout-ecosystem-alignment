# Source-paired profile provenance

This instrument capability does not authorize a campaign. The coordinator still
pins the exact source pair, image, instrument and acceptance receipt. Existing
094 diagnostic evidence is immutable and does not acquire these new fields.

`python3 tools/mt-bench/m7-joined/adapter.py capabilities` emits the tracked,
versioned [capabilities.json](capabilities.json), without Docker or cloud access.
The reserved deployment transport must verify this contract and the committed
`adapter.py manifest` content hash before activating its pilot. This lane does
not change that transport or activate a pilot.

`prepare --diagnostics off|on --diagnostics-interval-ms 5000` defaults to off.
The interval range is1000..60000ms. Only `NS_M7_DIAGNOSTICS` and
`NS_M7_DIAGNOSTICS_INTERVAL_MS` are set; ambient NS variables remain excluded.
The frozen Compose environment, generated private environment overrides and
actual running-container environment are checked. Unsupported numbered worker
roles refuse rather than silently escaping diagnostics/log inventory.

The per-run settings fingerprint (`fingerprint.cjs`) was removed on 2026-11-18.
It re-derived a settings projection from core source blobs at the paired commit
and refused any source layout it had not seen, which stopped runs on source
moves rather than on a product property. Run identity is the image digest plus
the run configuration. The k6 `r_status` read remains an ordinary status read.

`profileSelection` (version 4) contains version,
diagnostics selection, topology and a canonical SHA256 over those fields.
It deliberately excludes tenant count and API replica count. All pilot levels
and all same-workload API-scaling cells must carry the exact same object/hash.
Changing diagnostics or realtime/evaluator topology creates a distinct
profile; it cannot be called API replication alone. Pilot `--replicas 1|2|4`
selects one fixed count across500/750/1000 (default1); `profileReplicas` records
that choice. Fixed2 is a pilot profile, not evidence of API scaling. Full-ladder
strictness remains distinct from a coordinator-pinned capacity milestone.

Current topology is registry-default with verified `vault server` command and
no Vault Agent overlay. Server observations are never named Agent observations.
The existing Agent overlay conversion and component-scaling axes remain outside
this default-profile capability. No overlay is activated here.

Before teardown, the adapter captures private fixed-role log tails with5seconds
per role,64KiB per role and512KiB total caps. It kills timed-out/bounded producers
and records truncation, timeout, return code and failures in private
`role-logs/manifest.json`. Files are0600/directories0700; they can contain secrets
and must not be published. Missing or truncated output proves no absence. Log
collection failures do not replace the existing teardown operation. k6 resource
observations are retained under `windows.*.loadGenerators`, separately from
serving roles; exited k6 RSS is UNMEASURED, never fabricated. Missing serving
snapshots, RSS or samples make measurements incomplete.

Focused checks:

```bash
M7_PROFILE_TEST_CORE=/private/owned-pinned-core \
M7_PROFILE_TEST_COMMIT="$CORE_SHA" \
python3 -m unittest discover -s tools/mt-bench/m7-joined -p 'test_*.py' -v
```

The explicit core fixture needs its own exact-lock dependencies. It starts only
the actual status router over local HTTP with synthetic authorization, then
executes generated workload shapes under deterministic HTTP mocks. This proves
projection compatibility and mismatch detection; it is not the full serving
stack, stock k6 scheduler, capacity or component scaling acceptance. Ordinary
unit discovery without the explicit core fixture skips that source-specific
case and cannot be cited as its proof.
