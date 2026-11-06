# DRAFT — multitenant REST preview and explicit backend composition

This preview runs through the explicit `nightscout multitenant api` executable
with PostgreSQL/RLS, Vault Transit and persisted current authorization. Explicit
domain configuration admits the implemented legacy v1/inherited-v2 and API3
handlers, derived properties/ddata/summary and safe context. Default single keeps
MongoDB. Subject management remains a separately authenticated standalone JSON
factory; owner/operator listeners and policy are not enabled.

This continuation separates logical domain metadata from explicit PostgreSQL
factories/catalogues, read-only schema readiness and serving-privilege checks.
Shared dependency-failure recognition now sits below version-specific HTTP
rendering, preserving submitted-validation provenance and current response
semantics. Direct imported-identity tests compare actual Mongo/PG HTTP replies
and persisted typed IDs across edits/replacement/deletion with foreign-tenant
invariance. Current query/write policies and startup refusals are preserved.

Recorded on local `bc4ee1a91b84a657012dbb77ee835fdeb78ef707` (alignment R44):
complete nonbrowser 7035 passing /80 pending /0 failing; default browser684/0/0;
archived composition15 and direct identity15. Scopes overlap. Removed injected
capability and catalogue guards make real children bind unexpectedly; missing
dependency classification changes HTTP503 to500; missing PG raw-ID fallback
changes actual GET200 to404. These controls fail semantically and restored gates
pass. Independent source review, tier classification, changed-file lint and
final prcheck pass.

Independent #8891 writer replay is measured separately and is not included.
Existing source-pinned client-pattern replay is not client-binary execution.
Broader portable capabilities, helper consolidation, remaining REST side effects,
owner identity/ceilings, import/resources, lifecycle and durable realtime/evaluator
recovery remain open. No M0–M6 promotion, RC admission or production enablement
follows. Fresh remote CI/CodeQL must cover this continuation after publication.

[Current evidence and limitations](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/docs/30-design/remedial/rc-16.0.0-integration-record.md#r44---explicit-backend-composition-and-imported-identity-on-bc4ee1a9-2026-11-05)
