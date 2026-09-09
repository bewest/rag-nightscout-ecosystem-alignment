# Tooling Evaluation: keyv, mongoose, zod, wasm

**Date:** 2026-09-14
**Context:** requested alongside schema-vocabulary/typed-support planning
(`feature-backlog-prioritization.md`) — "consider use of popular and
appropriate tools (keyv, mongoose, zod, wasm, etc.) when appropriate."
**Method:** grounded against `cgm-remote-monitor`'s actual current
dependencies/code (checked directly, not assumed) plus two pieces of prior
art already in this repo: `docs/10-domain/priority-pr-deep-dives.md` (mongo
driver upgrade PR notes) and `docs/90-decisions/adr-005-adapter-protocol.md`
(WASM previously evaluated and rejected for a *different* purpose).

## 1. Current baseline (verified in `cgm-remote-monitor`, `dev@a8888f0d`)

| Concern | Current implementation |
|---|---|
| DB driver | Raw `mongodb` npm driver `^5.9.2` (upgraded from legacy 2.x per `priority-pr-deep-dives.md`; **mongoose explicitly evaluated and marked "Not used"** in that PR's dependency table) |
| Request-body validation | Hand-written imperative checks per endpoint, e.g. `lib/api3/generic/create/validate.js`: `typeof(doc.identifier) !== 'string'` style field-by-field checks, no schema object, no generated types |
| Schema documentation | OpenAPI 3.0 YAML specs exist (`specs/openapi/aid-*-2025.yaml` in *this* repo) but are **not wired into `cgm-remote-monitor` at runtime** — `swagger-ui-dist`/`swagger-ui-express` in that repo only serve interactive docs, they don't validate incoming request bodies |
| Schema validation library | `ajv` is present only as a **transitive** dependency (pulled in by something else — not required directly by any `lib/` file; confirmed via `grep -rln "require('ajv')" lib/` returning nothing) |
| Caching | Bespoke in-process caches (`lib/api3/storage/mongoCachedCollection/`, `lib/data/dataloader.js`) — no cache abstraction library, no external cache backend (Redis, etc.) |
| Cross-language runtime | None currently — all algorithm code is plain JS; WASM has never been used in `cgm-remote-monitor` |

## 2. `zod` — recommended, narrow scope

**What it solves here:** the API3 `validate.js` files across
`lib/api3/generic/{create,update,patch}/validate.js` are hand-rolled,
duplicate logic across the three operation types, and drift from the
OpenAPI specs in `specs/openapi/` (this repo) with no compiler/linter check
tying them together. Zod schemas would let one canonical schema definition
generate: (a) the runtime validator, (b) a TypeScript type (if/when the
codebase adopts TS or JSDoc `@type` annotations), and (c) — via
`zod-to-json-schema` — a JSON Schema fragment that could be diffed against
the hand-maintained OpenAPI YAML in this repo to catch drift automatically.

**Tradeoffs vs. current hand-rolled checks:**
- Pro: single source of truth, better error messages, composable
  (`.extend()`/`.merge()` for the create/update/patch variants which
  currently triplicate logic).
- Con: adds a dependency to a codebase that has deliberately stayed
  dependency-light on the validation side (no ajv, no joi); needs a
  migration PR, not a drop-in.
- Con: zod is TypeScript-oriented; in a plain-JS codebase you get the
  runtime validation but lose the compile-time type-checking benefit
  unless JSDoc + `checkJs`/TS-lite tooling is also adopted — **this makes
  zod adoption a sub-decision of the broader "schema vocabulary/typed
  support" question already flagged as too-broad-to-sequence in
  `feature-backlog-prioritization.md`**, not a standalone one.

**Recommendation:** don't adopt zod in isolation. Fold it into the existing
"schema vocabulary" backlog item as the *implementation mechanism* for API3
validation once that broader item is scoped (see §5).

## 3. `mongoose` — not recommended, reaffirming prior decision

This was already evaluated and explicitly rejected in this codebase: the
`priority-pr-deep-dives.md` PR notes for the driver-upgrade PR
(`wip/replit/with-mongodb-update`) list `mongoose: N/A / Not used` in its
dependency table. Nothing since has changed that calculus:

- The raw driver upgrade to `mongodb@^5.9.2`/`^6.x` was completed
  specifically to avoid the larger blast radius mongoose would add
  (schema-level document mapping, its own connection-pool semantics,
  discriminator/plugin ecosystem) on top of an already-large upgrade.
- `cgm-remote-monitor`'s collections (`entries`, `treatments`,
  `devicestatus`, `profile`) are read/written by many independent modules
  (`lib/api/`, `lib/api3/`, `lib/data/`) that would all need simultaneous
  migration to mongoose Models to get any benefit — a much larger and
  riskier refactor than the targeted zod validation change in §2, for
  largely the same validation benefit.
- **Recommendation:** keep the raw `mongodb` driver. If document-shape
  validation is wanted at the DB layer (not just at the API boundary), use
  MongoDB's own native [JSON Schema `$jsonSchema` collection
  validators](https://www.mongodb.com/docs/manual/core/schema-validation/)
  instead — no new npm dependency, enforced server-side regardless of
  which code path writes the document, and it can be generated from the
  same OpenAPI/zod schema as a build step.

## 4. `keyv` — situational, tie to Nocturne's Redis precedent

**Current state:** `cgm-remote-monitor` has two bespoke in-process caches
(`lib/api3/storage/mongoCachedCollection/`, `lib/data/dataloader.js`), no
external cache, no cache abstraction library. This works today because
Nightscout instances are typically single-process/single-instance
deployments (per `docs/reports/nightscout-release-planning-2026-09/`'s
prior finding that most deployments sit behind a single-instance PaaS
process, not a horizontally-scaled fleet).

**Why it's relevant now:** `docs/10-domain/nocturne-deep-dive.md`
(`Nocturne is a complete .NET 10 rewrite... Cache: Redis`) documents that
the from-scratch reimplementation chose Redis over in-process caching from
day one — a signal that a multi-instance/horizontally-scaled Nightscout
deployment story is being actively explored elsewhere in the ecosystem.
`keyv` is the natural fit *if and only if* `cgm-remote-monitor` ever needs
to support multi-instance deployments (shared cache/session state across
processes): it provides one small abstraction (`get`/`set`/`delete`) over
pluggable backends (in-memory, Redis, SQLite, MongoDB itself via
`@keyv/mongo`), so the existing bespoke caches could be swapped for `keyv`
with an in-memory adapter today (zero behavior change) and a Redis adapter
later (zero code change, config-only) — cheaper than hand-rolling
Redis-specific cache code later.

**Recommendation:** not urgent. Worth a small, low-risk PR replacing
`mongoCachedCollection`'s internal `Map`-based storage with `keyv` +
`@keyv/memory` (behavior-preserving), specifically so that a *future*
horizontal-scaling effort (if one is ever proposed, following Nocturne's
lead) only needs a config change, not a re-architecture. Do not couple this
to the current release; flag it as a "cheap now, expensive later"
opportunistic item.

## 5. `wasm` — reopen narrowly, don't re-litigate ADR-005

`docs/90-decisions/adr-005-adapter-protocol.md` already evaluated and
rejected "compile everything to WebAssembly" — but **for a specific,
narrower purpose**: using WASM as the *common runtime* for the
cross-validation harness that compares oref0(JS)/oref0(Swift)/oref0(Kotlin)
outputs. That rejection was correct and remains correct for that use case
(rationale given: "Swift-to-WASM toolchain is immature... would lose
native runtime behavior that we're specifically trying to validate" — still
true, we are not revisiting that decision).

**What's different now:** `docs/10-domain/nocturne-deep-dive.md` documents
a **separate, already-shipped** use of WASM in this ecosystem: Nocturne's
`src/Core/oref/` is a native **Rust** implementation of oref0/oref1 (IOB,
COB, dosing) with a `wasm` Cargo feature via `wasm-bindgen`, explicitly for
**browser-side calculation** (not cross-validation) — "WASM Support: ✅ —
Browser-side calculations." This is existence-proof that Rust-to-WASM (as
opposed to Swift-to-WASM, which ADR-005 correctly rejected) is mature
enough for production oref calculations today, in this exact problem
domain.

**Recommendation:** this is worth a **narrow, separate** research/proposal
item — not a reversal of ADR-005, but a new question: *should a
reference-implementation oref0/oref1 core be extracted to Rust+WASM,
runnable identically in Node (via `@node-rs`-style native bindings or WASM)
and in-browser (e.g., for a future `cgm-remote-monitor` reports/simulation
UI, or the Svelte-based reports UI already discussed in
`docs/60-research/nightscout-modernization-next-steps-2026-09-09.md`)?*
This would let `cgm-remote-monitor` and Nocturne's web frontend share one
oref implementation instead of maintaining parallel JS and Rust ports, and
could *feed into* the ADR-005 cross-validation harness as a fourth adapter
(Rust/WASM) rather than replacing the harness's stdio protocol. Flag as a
new backlog candidate, cross-referenced from both ADR-005 and
`feature-backlog-prioritization.md`, not started here.

## 6. Summary decisions

| Tool | Decision | Scope |
|---|---|---|
| `zod` | Adopt, but only as part of the broader schema-vocabulary item | Fold into that item's design, don't start standalone |
| `mongoose` | Do not adopt — reaffirmed | Use MongoDB native `$jsonSchema` validators instead if DB-layer enforcement is wanted |
| `keyv` | Adopt opportunistically, low priority | Small behavior-preserving swap of internal cache storage; unlocks future Redis option cheaply |
| `wasm` | New narrow proposal, not a reversal of ADR-005 | Rust/WASM shared oref core (Node + browser), informed by Nocturne's shipped precedent; feed as a 4th adapter into the existing cross-validation harness rather than replacing it |
