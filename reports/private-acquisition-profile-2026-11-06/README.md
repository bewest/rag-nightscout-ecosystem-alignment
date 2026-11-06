# Independent profile private-acquisition acceptance

*Contributor-facing immutable capture, 2026-11-06. Acceptance facts are in [acceptance.json](acceptance.json); this page summarizes that capture.*

Accepted bounded independent profile `2ee8b493d76ddf92bf53d5e5c9cf0d9d0d2dbb35` over `5173864da1835da7aecf1f73121b28463f6a6a70`. Only the private acquisition helper and views allocation/loader composition changed. The helper is byte-identical to the accepted REST helper; independent `evaluateCycle` remains. This tree belongs to #8891 and is separate from #8898.

Runtime figures are **reproduced**. Policy preservation is **read-derived** from exact source equivalence and supported by the scoped runtime checks.

## Measured verification

| Campaign | Passing | Pending | Failing |
|---|---:|---:|---:|
| Archived profile | 38 | 0 | 0 |
| Restored archived profile | 38 | 0 | 0 |
| Complete nonbrowser | 6690 | 3 | 0 |
| Fresh default browser | 684 | 0 | 0 |

All positive campaigns exited zero; each negative control exited one for its stated semantic assertion. Counts overlap and must not be summed as independent coverage. Changed-file lint has no findings; the 456-file/eight-tier map and nine adapter entry points pass. Fresh final prcheck reports OK, contains official dev `4a482627bfdafb1fef8dcbe0ac6c484811cae563`, and leaves the tested head clean and unchanged.

## Semantic controls

| Control | Detected failure | Result |
|---|---|---|
| `http` | post refreshes one coalesced retained cycle | 0 passing, 1 semantic assertion failure |
| `frame-clinical` | next actual trigger observes entries B | 0 passing, 1 semantic assertion failure |
| `frame-retention` | failed materialization preserves the previous timestamp and clinical properties | 0 passing, 1 semantic assertion failure |

The trigger control exercises actual HTTP mutations. The clinical control changes the shipping setter on the selected cohort. The retention control clears the previous successful result after a selected callback failure following real rows. All restored profile checks pass; setup errors and zero tests do not count as controls.

## Pins and runtime

- Application: `2ee8b493d76ddf92bf53d5e5c9cf0d9d0d2dbb35`; profile base: `5173864da1835da7aecf1f73121b28463f6a6a70`.
- REST helper source: `ee480a96f8ce481c0fcbfb202a0fc0afeaade032`; identical helper blob: `3a97307af1e749e98b99f2955182e6844c331441`.
- Lock SHA-256: `74c52ff603dc82e45717bd2b8618e515c76486f49ca4373db420911ad0641119`.
- Gate blob: `385ed9775168defd07f6d2d5708a5d0b5a366539`; broad runner blob: `1051550d9a47053633042c221926968c86802f5f`.
- The alignment document fast-forward between the two pinned commits in JSON preserved both instrument blobs; no test input change or repeat was needed.
- Node v22.23.4, MongoDB 8.0.34, PostgreSQL 16.15 and Vault 2.2.1; UTC, seed 41574423920.
- The evaluator runs on MongoDB. The general runner supplies PostgreSQL and Vault; that does not establish a PostgreSQL evaluator. Default browser acceptance is separate from a complete cross-engine matrix.

## Cleanup and privacy

Seven serial campaigns captured 11 containers and 20 volumes. Every captured resource was independently confirmed absent after cleanup. The audit records successful detached creates, operates on exact current IDs and does not guess orphan ownership. Failed creates without returned IDs and unknown, named or attached resources are outside its scope; this is not a universal zero-leak claim.

The public capture contains synthetic-fixture aggregates and source/dependency pins. It excludes machine paths, resource identities, service addresses, runtime configuration, credential values, record bodies and traces. Private dependency and service selection values are intentionally omitted.

## Boundaries retained

- Private per-acquisition helper and materialized targets remain distinct; caller cache and bus are not inherited.
- Independent evaluateCycle definition and export retained; REST helper bytes and views allocation hunks match exactly.
- Existing bounds, future-record handling, statistics failures, typed-identity union, evaluation cadence and retained-result policies unchanged.
- Actual selected concurrent-read schedule remains mixed entries A and treatments B, followed by B and B on a real trigger.
- Selected callback failure is injected after real rows arrive; it is not a real database-outage test.

## Remaining limits

- No common database revision, stronger snapshot isolation, settings or plugin version key guarantee.
- No logical subscriber switch, executable v1 or socket admission, default-role change, or REST branch join.
- Teardown checks establish no late fake-provider delivery; they do not establish database cancellation, absence of internal handoff, or immutable closed state.
- Complete clinical and writer cohorts, live statistics freshness, runtime cost, durable notification state and multitenant recovery remain open.
- No milestone promotion, release placement or production enablement. All commits remain local at capture; no push by this lane.
