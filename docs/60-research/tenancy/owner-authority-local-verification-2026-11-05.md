# Owner authority local-verification measurement — 2026-11-05

*Contributor-facing immutable measurement record; reproduced by this session.
Captured UTC 2026-11-06T03:24:57.386Z, November 5 in America/Los_Angeles. This is a bounded
prototype, not production acceptance, a release change or a milestone promotion.*

## Anchors and instrument

- Alignment instrument: `e8c3c01ed480e12cd0a1568eb6af29743fe9c30c` (clean committed instrument; record/queue additions followed).
- Actual CRM baseline modules: `d4570e585d0e12e46386ed26772790b269b2b736`; source worktree was clean at inspection.
- Node `v22.23.4`, PostgreSQL `16.15 (Debian 16.15-1.pgdg13+2)`, Vault `2.2.1`.
- [Adopted contract](../../30-design/tenancy/owner-authority.md).
- [Instrument and command](../../../tools/lab/owner-authority/README.md).
- [Raw timings/call counts and SHA256 instrument provenance](../../../tools/lab/owner-authority/results/2026-11-05.json).
- [Negative-control results](../../../tools/lab/owner-authority/results/2026-11-05-controls.json).

## Question and prediction

Can new-format local public-key verification remove routine Vault calls while
preserving current-authority refusal and next-operation revocation? Does combining
current checks reduce repeated authority snapshots, particularly write attribution?
Prediction before running: current has 2 Transit calls, 2 secret-audit commits and
2 legacy metadata reads per operation; local arms have none. Existing authority
needs 1 snapshot for read and 2 for write; combined candidate needs 1 for either.
Local paths should reduce latency, without assuming a production speedup factor.
The diagnostic local-shipping arm isolates credential-path removal; it does not
implement the combined candidate's additional session/key state.

## Reproduced results

16 named semantic checks passed; 4 independently broken implementations failed
at their expected assertions. 24 timing cases, 120 operations each, 2,880 timed
operations total, plus excluded warmups. Two repeats reverse arm order; two
independently pooled workers, concurrency 1 and 8. All logical call-count assertions
matched the predictions. The counters are not PostgreSQL wire-round-trip counts.

Each timing pair is repeat 1 / repeat 2; milliseconds for p50/p95. These are separate
sample distributions, not pooled percentiles or confidence intervals.

| Concurrency | Authorization | Arm | p50 ms | p95 ms | operations/s |
|---:|---|---|---:|---:|---:|
| 1 | read | current | 13.985 / 16.938 | 23.283 / 20.940 | 66.135 / 63.906 |
| 1 | read | local-shipping-authority | 1.017 / 2.490 | 2.188 / 3.000 | 872.685 / 431.164 |
| 1 | read | local-combined | 0.680 / 0.819 | 1.136 / 2.224 | 1353.926 / 941.894 |
| 1 | write | current | 19.520 / 19.294 | 24.890 / 24.546 | 54.602 / 55.062 |
| 1 | write | local-shipping-authority | 4.552 / 4.175 | 5.799 / 5.704 | 226.009 / 268.968 |
| 1 | write | local-combined | 1.470 / 1.561 | 2.958 / 2.853 | 619.456 / 622.584 |
| 8 | read | current | 17.646 / 15.293 | 26.526 / 25.435 | 414.434 / 499.151 |
| 8 | read | local-shipping-authority | 2.303 / 1.967 | 4.271 / 3.001 | 2962.361 / 3749.411 |
| 8 | read | local-combined | 2.315 / 2.293 | 3.731 / 4.812 | 2929.700 / 3080.633 |
| 8 | write | current | 16.737 / 15.549 | 28.373 / 21.238 | 448.009 / 491.773 |
| 8 | write | local-shipping-authority | 3.455 / 3.530 | 4.262 / 4.655 | 2296.354 / 2209.567 |
| 8 | write | local-combined | 2.037 / 1.986 | 2.806 / 2.718 | 3680.392 / 3821.919 |

The largest consistent architectural saving is removal of root decrypt, remote
verification and their synchronous audit/metadata work. Combined snapshots also
remove a duplicate current-name/grant read for writes. At concurrency 8 the combined
read path is not consistently faster than local verification with the shipping
reader; it additionally checks session/tenant/key state. Shared-host variation
precludes choosing production pool sizes or capacity from these figures.

## Revocation, isolation and outages

- Actual current-path and new-path earlier tokens pass before an uncommitted grant
  removal, then refuse on the next operation after commit on both independent pools.
- Candidate tenant suspension, session revocation/expiry, credential generation
  change and key retirement refuse across pools; a cached public key grants no bypass.
- Both tenants' distinct Vault-generated keys verify their own tokens. A token used
  against the other tenant fails as `TOKEN_SIGNATURE`, with positive own-tenant controls.
- Invalid signatures, issuer/audience/purpose/tenant, times, unknown keys, algorithm/
  URL injection and noncanonical encodings refuse. Forced RLS filters an omitted-predicate read.
- Stopped Vault: cached-key candidate reads/writes continue; current legacy verification,
  new issuance and secret decrypt refuse. Revocation remains enforced while Vault is down.
- Stopped PostgreSQL: local signature verification succeeds, but new protected reads/
  writes refuse. This stop follows the Vault stop; it is not a separate healthy-Vault
  baseline PostgreSQL-outage performance experiment. An independent injected-authority
  error check also refuses without reusing prior grants.

## Non-vacuous controls

The controls modify only scratch copies of the actual prototype. Each exits nonzero
with the named ERR_ASSERTION rather than a setup failure:

| Break | Exact detected symptom |
|---|---|
| Remove cryptographic signature comparison | Tampered signature expected to refuse before PostgreSQL instead succeeds |
| Remove audience comparison | Correctly signed wrong-audience token expected to refuse instead verifies |
| Remove session-active enforcement | Earlier token expected to refuse after committed session revocation instead authorizes |
| Reuse earlier authority snapshot | Earlier token expected to refuse after committed grant removal instead authorizes |

## Traps and limits

Earlier pilots are diagnostic, not acceptance. Container-internal `pg_isready` saw
PostgreSQL's initialization server before TCP startup completed; the runner now probes
its actual TCP connection. Vault's Ed25519 key metadata supplies raw base64 bytes,
not PEM; conversion uses public JWK encoding and checks length. A pilot synchronously
stopped PostgreSQL and immediately checked out sockets before idle closure events
drained, producing unhandled `Connection terminated unexpectedly`. The final run
lets those events drain before measuring a settled outage. In-flight shutdown races
remain UNMEASURED; no production connection code was changed. The interrupted pilot's
owned containers were separately identified and removed.

All data and services are disposable/synthetic; no existing Vault mounts/keys or
peer databases were touched. Services are cleaned after each final/negative-control
run. Vault development mode, loopback HTTP, preprovisioned public keys, fixed denied
defaults/provisioned roles and candidate state tables do not establish production
TLS/HA/recovery, full legacy defaults, complete owner ceilings, session/refresh issuer,
provider renewal, distributed streams, concurrent shutdown, key distribution/rotation
or end-to-end handler/client throughput. No application full suite is claimed: no
CRM source was changed. This benchmark must precede a separately reviewed dormant
application integration and complete compatibility/security regression.
