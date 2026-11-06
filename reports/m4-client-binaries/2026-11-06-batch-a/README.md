# Combined Batch A actual-client campaign — 2026-11-06

*Contributor-facing immutable measurement, archived CRM `863c8a2b3fa7ac3e13ecb5f7dca90de6766bb7e0`, committed alignment instrument `c724b38aaaffa05d8404e64f36ce0d9b3fe26da2`. Current item state lives in `queue/work-queue.yaml`. CRM file citations below refer to this archived head.*

**Reproduced:** one combined actual-client campaign, 106/106 checks passing, 21 cells on each
stack, one unexplained difference. Gate exit 1. No missing cells. This does not promote
`M4-CLIENT-LAB` or the M4 milestone. No classifier exception or application repair was made
by this lane. Root owns the dedicated refusal repair, revised freeze and acceptance.

The campaign ran cgmsim, oref0, Share-fed connector and connector source mode in one run,
with one fixed-data Share poll per cycle. It archived the same application head for both
single-site Mongo and the explicit two-tenant PostgreSQL/Vault preview. Independent oracles
and denied anonymous access were retained. All data and identities were synthetic; no vendor
account was contacted. The gate freshly verified all 94 cgmsim runtime JS files against a
clean source compilation before starting fixtures. Client pins, runtime/image identities,
checks and capture hashes are in the [summary](summary.json).

## Paired outcomes

| Surface | Reproduced outcome on this frozen head |
|---|---|
| Entry identity migration | Previously differing cell matches exactly: HTTP 200 array of two replies, process exit 0 on both, corresponding identifier preserved in both stored outcomes. |
| oref0 header latest-treatment lookup | Previously differing cell matches exactly: HTTP 200 array of one reply, process exit 0 and equal logical client output/store on both. |
| oref0 malformed token lookup | Both HTTP 401, process exit 5, no logical storage change. Mongo reply keys description/message/status; preview reply key error. This is the sole unexplained cell. |
| Connector Share and restart | Exact fixed synthetic readings and stored values match; no duplicate on restart. Incremental new-reading behavior remains UNMEASURED. |
| Connector source | Actual preview exchange/read and single-site sink POST succeed; exactly the three A source rows reach the empty sink, B unchanged. This is an observation, not baseline-as-source differential. |
| Refusals | Actual cgmsim/oref0 cross-tenant, revocation and unknown-alias carriers refuse with the recorded statuses; snapshots of all compared domain values stay unchanged. Missing-secret oref0 upload refuses locally; no-carrier write is a separately labelled protocol probe. |

[Classification](classified.json) retains the complete difference. The reused mechanical
classifier labels unchanged stored values as group q; the cell has no accepted explanation.
The [older frozen-head record](../2026-11-06/README.md) and its failed controls remain unchanged.
Their exact instrument checks are not repeated as leaf campaigns here. This run provides the
requested combined-head actual-client measurement; no full/browser/corpus campaign ran in M4.

## Remaining refusal contract and recommendation

**Read-derived contract finding, with reproduced wire difference:** the preview's legacy
middleware already emits `status:401`, `message:Unauthorized`, and a static description at
`lib/server/tenant-app/legacy-authorization.js:37`. Earlier authentication rejection enters
`identity` at `lib/server/tenant-app/index.js:57` through `:192`, then uses the generic error
renderer at `:107`; current-authority refusal uses `:114-115`. The legacy surface therefore
has different envelopes depending on the refusal stage.

The single-site contract is explicit in `tests/api.unauthorized.test.js:60-62`: status 401,
message Unauthorized and a description are required. Preview `lib/server/tenant-app/README.md:252-258`
authorizes strict refusal instead of anonymous fallback; it does not adopt loss of these fields.
The exchange contract at `:163-168` also preserves the shipping 401 status object. Oref0's
same jq failure on both replies measures this client's observed outcome; other clients' error
parsing remains UNMEASURED.

Recommendation to the coordinator, **read-derived and not an adopted policy**:

| Criterion | Recommendation |
|---|---|
| Long-term direction | Preserve the established sanitized v1/v2 refusal envelope. |
| Architecture | Render it at the trusted legacy data boundary. Use composition-owned plane/version metadata: owner routes also use `/api/v1`, so a path-prefix rule would cross contracts. |
| Backward/forward compatibility | Keep strict credential refusal and current authority checks; retain the existing v3 and owner/operator error contracts. Keep this classifier cell unexplained until measured parity or an explicit decision. |
| Maintenance | Centralize the static legacy formatter across authentication and permission failures. Preserve sanitized 503 handling. |
| Reliability | Keep authorization/storage admission unchanged and prove refused operations have no stored effects. |
| Performance | Formatting should require no additional database or Vault call; latency and capacity are UNMEASURED. |

Root assigned a separate source-only compatibility repair after this finding. This capture
remains on 863; any descendant result requires its own exact-head measurement. No previous
capture is relabelled or silently waived.

## Ownership and limits

All owned fixture containers were verified absent; no new containers or volumes remained.
The runtime slot was released after this capture. Lane detail and transfer instructions:
`externals/work/HANDOFF-codex-m4-20261106.md` (local, untracked). Root allocates the next R entry
from the final combined records; this report does not reserve R59.

Connector-specific refusal controls, new-reading polls, baseline-as-source/non-entry source
comparison, reject-mode malformed batches, mobile/v3 binaries, sockets/D23 forwarding, TLS,
outage soak and performance remain UNMEASURED. B5 owns one full/browser/expanded-corpus/final
prcheck campaign after the coordinator's revised freeze. No application push or milestone
promotion was performed by M4.
