# Repaired pair: initial subscription timeout and bounded observation

Captured 2026-11-12. **Clinical paired qualification remains open.** This leaf
preserves a reproduced initial-readiness failure and a later passing read-only
observation; the cause of the original timeout remains unclassified.

Runtime source: `cd4629159809fb3cffbc6f57626f98f3ffdbdda7`.
Runtime binding/image input: `0f8749bc954812b9d384528da733680930e3b236`.
Actual image: `sha256:454d58b4d30a7a34f9d02005aab44dd7868cd3db6eb27e0f30fcbd623f91feab`.
Selected topology: two API workers, two realtime workers/two logical shards,
three fixed evaluator participants with effective membership initially two,
Vault SERVER, diagnostics OFF. The fresh repaired owned state is retained.

The stock/restore fixture passed with 141 B settings reads across four workers
and zero read errors; lower-port settings authority controls passed. The clinical
fixture then failed at its initial combined 20-second subscription/frame wait,
before clinical uploads or evaluator membership mutation. Its original output is
[retained unchanged](captures/original-timeout.log). It did not record which of
A alarm ACK, B alarm ACK or B main frame was absent. No clinical or move pass is
claimed from this attempt.

## Diagnostic-only instrument and control

Host instrument `b89cd8fa76c438f88766db48e5e99521cd3d51bf`, followed by
`d229e3a9cd8948c35731e0f1f937bc91387f6f77`, adds typed socket summaries and a
standalone pre-mutation observer. The running image is not relabeled with these
host-test commits. Runtime-consumed inputs are unchanged. The successful
predicate, websocket options and 20-second deadline are unchanged; authorize ACK
is diagnostic only. No upload, configuration, membership or lifecycle write is
added. Summaries exclude token/secret/URL/frame/alarm bodies and cap each ACK tail
and event history at 64 with ACK counts/truncation.

[Focused diagnostic/oracle checks](captures/focused-diagnostic-oracle.log):
11 pass, zero skipped. They distinguish rejected subscription/authorization,
connection error and missing initial frame. Independent review reproduced an
unbounded ACK-summary gap in b89; the new repeated-ACK control fails that original
helper with `200 !== 64` and passes d229. The
[original-code control](captures/original-unbounded-summary-control.log) preserves
that red result. Raw test arrays and successful predicates remain unchanged.

## Single authorized read-only prerequisite observation

Executed host driver:
`bindings/compose/multitenant/fixtures/evaluator-client-prerequisites.cjs` at d229.
Driver SHA-256 `3f3a639d28bb96066f7bae5e308a49297c79995ed83a2004bf974266e9fbead9`;
shared diagnostics helper SHA-256
`8e853db1e91561bd7a903e1bad72e003a92415bf3d1dd69ff9682b89736ecd97`.

[Actual typed result](captures/prerequisite-probe.json): passed in 216 ms within
the unchanged 20-second deadline. A alarm ACK arrived at 155 ms, B alarm ACK at
156 ms; B main initial frame and read/write authorization ACK arrived at 202 ms.
Each had one connection and no observed error/disconnect/reconnect. Both current
realtime workers reported HTTP 200, their assigned tenant ready, placement
generation one and held ownership resources in the
[bounded health capture](captures/current-realtime-health.json).

This later passage does not explain or clear the earlier failure. Alarm ACK
success alone does not prove read permission; main authorize ACK follows the
frame on the successful read path. Current health cannot reconstruct prior warm
state. A warm-timing hypothesis is read-derived, not reproduced. Existing private
protocol counters are not exposed by these public health responses and were not
fabricated by creating a new protocol instance. No full clinical mutation retry
or controlled realtime move was run during this diagnosis. The observer/collector
remains held until the coordinator's next boundary.

Capture hashes are in [sha256.json](sha256.json). All identities and data are
synthetic; no credentials or raw clinical payloads are included.
