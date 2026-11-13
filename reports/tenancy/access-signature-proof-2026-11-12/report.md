# Bounded local signature-proof evidence

Captured 2026-11-12. Product, controls and profile instrument:
`623181b7c07586f72cffcaaec716983863cdf28c`, parent
`55e875161a95a8ab1e60b751e29515fee92dd70c`. The baseline verifier was read
from `d357c661acb251e6dfda9e4237d59ee603156ccb`; its SHA-256
`fe0f0569771162bcef5abb6b6aeb3d5fe282b92c9b481bd215c4e929c29d4b4d`
exactly matches the parent verifier before this change. Profile instrument
`scripts/profile-access-signature-proof.js` SHA-256:
`672a03acea3bd63fecf0807c63f4baab4ed780826412e5fedc0d528cd97cb91a`.

This immutable record measures a local verifier capability. It claims no whole
authorization, database, socket, heap, capacity, comprehensive acceptance or
release improvement. The legacy/Vault verification path is unchanged.

## Capability and fixed resource boundary

Only successful Ed25519 mathematical proofs are reused. Every call still
resolves its current trusted key descriptor and checks issuer/audience/purpose,
current FIPS mode, tenant, claims and expiry. Every authentication still obtains
current DB authority. No credential decision, grants, claim acceptance or
negative result is cached. There is no TTL/grace/revocation policy change.

A proof matches exact signed bytes and signature plus the current public
material. The identical immutable native KeyObject has the identical material.
A different object must match exact public DER before any reuse. A new object
under the same kid with changed material performs fresh crypto and refuses the
old signature. DER work occurs only on a potential hit across different
objects, avoiding unconditional encoding cost on cold misses.

One process-wide LRU has at most 256 positive entries, one MiB of ASCII encoded
proof keys and optional DER, and 16 KiB per entry. Native public-key references
are bounded by that same entry count; there is no per-tenant cache or separate
encoding LRU. Larger inputs stay uncached. Encoded byte accounting is not a
claim about V8 object overhead, native heap or process RSS.

## Reproduced acceptance

Captured outputs: [native](native.txt), [focused](focused.txt),
[controls](controls.txt), [tiers](tiers.txt), [lint](lint.txt).

| command | result |
|---|---|
| `NS_MANAGEMENT_SESSIONS_DOCKER_TEST=1 NS_API_ROSTER_SERVING_DOCKER_TEST=1 ./node_modules/.bin/mocha tests/management-sessions.integration.test.js tests/api-fixed-roster-serving.integration.test.js --reporter spec` | 23 passing |
| `./node_modules/.bin/mocha tests/access-signature-proof.test.js tests/human-access.test.js tests/human-session-stream.test.js tests/human-session-integration.test.js tests/realtime-preview.test.js tests/realtime-bootstrap.test.js tests/registry-config.test.js --reporter dot` | 82 passing |
| `node scripts/test-signature-proof-control.js` | all three independent owned-scratch ablations discriminate |
| `node scripts/test-tiers.js check` | 690 test files, 8 tiers, okay |
| ESLint affected helper, verifier, tests and instruments | zero errors, one developer-instrument dynamic-require warning |
| `git diff --check` before source commit | exit 0 |

The new unit suite's eight cases establish reduced repeated crypto work while
current key resolution and authority snapshots still run for sequential and
concurrent attempts. It primes a valid proof, then refuses corrupted signatures,
changed signed bytes, removed keys, changed purpose, same-kid changed material,
wrong tenant, expiry and revoked current authority. Lookup-only expiry semantics
do not carry into ordinary verification. Different objects with identical DER
can reuse the proof; changed DER cannot. A controlled FIPS-mode discriminator
forces fresh math work; no live FIPS deployment acceptance is claimed.

The entry-bound control makes an evicted proof perform crypto again. The byte
control reaches the encoded budget before the entry count, then independently
checks oversized proofs stay uncached. Owned scratch removes each limit in turn:
entry ablation goes red at `257 !== 258`, byte ablation at `140 !== 141`.
Replacing the full proof key with a constant accepts a corrupted signature and
makes the expected TOKEN_SIGNATURE assertion go red with `Missing expected
exception`. Working source and peer worktrees are never mutated by controls.

Native tests use uniquely owned PostgreSQL/Vault and actual API CLI processes,
current management-token authority and private lifecycle transports. Current
revocation, wrong-tenant denial, expiry, key policy, cross-replica grants and
response/restore lifetimes remain green. Non-API lifecycle peers remain
synthetic status/invalidation participants. All owned resources are cleaned.
These are focused capability checks, not a full all-role deployment campaign.

## Profiles and cache churn

The instrument runs `node --expose-gc scripts/profile-access-signature-proof.js`
with an absolute baseline or candidate verifier module path. Cases add
`--unique`, `--working-set 1000`, `--working-set 3000`, or
`--working-set 3000 --spread-bursts`. The working sets use distinct synthetic
tenant/key/credential triples, two consecutive consumer verifications per
credential, and two rounds. Interleaving separates the consumer attempts across
the whole working set. These model one worker; they are not real socket
connections or proof sharing across processes. The host was not isolated.

| workload | attempts | baseline crypto calls | candidate crypto calls | candidate proof hits | baseline wall ms | candidate wall ms |
|---|---|---|---|---|---|---|
| one warm credential | 10000 | 10000 | 0 | 100% | 946.03 | 62.63 |
| unique credentials, one public key | 1000 | 1000 | 1000 | 0% | 96.96 | 100.45 |
| 1000 triples, consecutive pairs | 4000 | 4000 | 2000 | 50% | 391.78 | 212.72 |
| 3000 triples, consecutive pairs | 12000 | 12000 | 6000 | 50% | 1152.02 | 651.11 |
| 3000 triples, interleaved | 12000 | 12000 | 12000 | 0% | 1234.70 | 1190.20 |

Current key resolutions equal attempts in every capture. The zero-hit timings
are individual nonisolated observations, not a cold-path speedup claim. A working
set larger than the fixed bound can churn completely; the proof cache does not
grow with it. The paired model still benefits from immediate reuse. Raw captures
include CPU and retained-heap observations, but neither allocation nor heap
improvement is claimed.

Raw profile pairs:
[hot baseline](hot-baseline.json), [hot candidate](hot-candidate.json),
[cold baseline](cold-baseline.json), [cold candidate](cold-candidate.json),
[1000 baseline](n1000-baseline.json), [1000 candidate](n1000-candidate.json),
[3000 baseline](n3000-baseline.json), [3000 candidate](n3000-candidate.json),
[interleaved baseline](n3000-interleaved-baseline.json),
[interleaved candidate](n3000-interleaved-candidate.json).

## Substantive intermediate failures

An eager-DER prototype added visible cold-churn work in exploratory measurements.
It was not adopted; the final implementation defers DER until needed. That
transient implementation was not committed or execution-hash pinned, so its
local diagnostic timings are not accepted comparison evidence. They remain in
the evolving local handoff. Final before/after captures above have exact source
and instrument attribution.

The first broad focused run produced 78 passes and two strict bootstrap reset
fixture failures. Investigation corrected an initial hypothesis: the actual
cause was valid compact FK syntax in management issuance DDL, while the fixture
required whitespace before the parenthesis. The coordinator repaired the closed
FK grammar and explicit reset-table closure in original commit
`55e875161a95a8ab1e60b751e29515fee92dd70c`, with its own red control. That
repair was merged before the final native and focused checks. No immutable
migration, RLS or runtime authority guard was weakened.

## Integration boundary

The coordinator owns original-history integration and the final coherent
full/browser/enabled-corpus and capacity acceptance. Those campaigns remain
UNMEASURED in this lane. This local math result must not be attributed to the
unchanged legacy/Vault path or used as whole-authorization capacity evidence.
The isolated alignment evidence checkout retains its already-reported missing
external gate-worktree prerequisite; no queue state or gate was changed to
manufacture programme acceptance.
