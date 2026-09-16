# Module-level shared state: what T3.3 has to fix before it can exist

**2026-09-15.** Measured with `tools/qc/tenant-shared-state.js`, output in
`reports/tenant-shared-state/crm-seam.json`, against
`externals/work/crm-seam` at `7cc03cda` (Phase 2 complete).

{M} §5.2 item 4 asks for "a lint rule or test banning module-level mutable plugin state". This
is the measurement that has to come first: a ban is only writable once you know what it would
ban, and **a ban nobody can satisfy gets switched off.** Item 3 — "tenant-scoped settings
object; every read of `env.settings` audited" — turns out to be a much larger statement than it
looks, for the reason in §2 below.

## 1. Why residency is the whole question

Under D4 the target is several tenants served by one Node process. A `var cache = {}` at module
scope is initialised **once per process**, not once per tenant, so it is shared by every tenant
that process serves. If it holds anything derived from a request, one person's data is reachable
from another's. If it holds anything a request can grow, one tenant can exhaust it for everyone.

Neither failure announces itself. The module keeps working and the tests keep passing, **because
a test process serves one tenant.**

But the same pattern in browser code is not a hazard at all: `lib/client/index.js` is the single
largest holder of module-level state in the tree, and it is loaded once per page, by one person,
for one site. A census that does not separate these is misleading rather than incomplete — it
reports 70 files and buries the 6 that matter.

So residency is computed from the **require graph**, not from directory names, because the
directories do not line up with it: `lib/plugins/` is loaded by both the server
(`plugins.checkNotifications`) and the browser bundles (the chart), which is precisely the
category that needs naming.

| residency | files | bindings | writes after load | hazard? |
|---|---:|---:|---:|---|
| **server** | 17 | 31 | **64** | yes — one process, many tenants |
| **both** | 13 | 27 | **7** | yes, for the server copy |
| browser | 40 | 92 | 152 | no — one page load, one person, one site |

**Only six files are server-resident *and* written after load.** That is the list Phase 3 has to
deal with, and it is short:

| writes | file | what it is |
|---:|---|---|
| 52 | `lib/server/env.js` | the settings singleton — §2 |
| 11 | `lib/storage/mongo-storage.js` | the connection singleton — §3 |
| 3 | `lib/plugins/speech.js` | dual-use plugin state |
| 2 | `lib/plugins/timeago.js` | dual-use plugin state |
| 2 | `lib/profilefunctions.js` | dual-use |
| 1 | `lib/storage/tenant-scope.js` | the tenancy mode, deliberate — §4 |

**A false-positive class this deliberately does not flag**: a frozen object, a primitive `const`,
a RegExp, a function, a `require`. Those are configuration, and a rule that flags them teaches
people to ignore it. What it *does* flag that a reader might not expect is **`const` bound to an
object or array** — `const` freezes the binding, never the value, and that is the single most
common way this pattern hides.

## 2. `env` is one object for the whole process, not one per call

`lib/server/env.js:13` declares `const env = {…}` at module scope; `config()` at `:33` populates
it and **returns that same object** at `:69`. Measured:

```
env.js: config() returns the same object twice: true
  a mutation is visible on the second handle: true
```

So **§5.2 item 3 is not "audit every read of `env.settings`" — it is that there is only one
`env` to read.** Two tenants cannot hold different settings, because the second `config()` call
overwrites the first's values in place rather than building a second object. Auditing the reads
matters, but it is the second half of the job; the first is that the thing being read is a
singleton by construction.

This is latent today: `bootevent` calls `config()` once per process. It stops being latent the
moment `ctxFor(tenantId)` (T3.3) wants two contexts with different settings.

## 3. The connection singleton returns one tenant's database to another

Worse, and measurable today. `lib/storage/mongo-storage.js:7` holds
`const mongo = { client: null, db: null }` at module scope; `:111` short-circuits on
`if (mongo.db != null && !forceNewConnection)`; and `:159` sets
`mongo.db = env.storageNamespace ? client.db(env.storageNamespace) : client.db()` **once, at
first connect.**

`STORAGE_NAMESPACE` arrived in T2.5 as per-run test isolation. Combined with the singleton it
produces this:

```
tenant A asked for probe_tenant_a, got: probe_tenant_a
tenant B asked for probe_tenant_b, got: probe_tenant_a
same store object returned to both tenants: true
```

The server says so in its own log line while doing it — `Reusing MongoDB connection handler`.

**Nothing calls `init()` twice with different namespaces today**, so this is not a live defect;
`bootevent` calls it once. But `ctxFor(tenantId)` is *precisely* the thing that would, and it
would get a silent cross-tenant read rather than an error. **T3.3 cannot be built on this module
as it stands**, and that is the useful output of this audit: the blocker is named before the task
starts rather than discovered inside it.

Note the contrast with the PostgreSQL backend from T2.5, which does not have this shape: its
isolation is a per-transaction `set_config` on a pooled connection, so two tenants sharing one
pool is the *designed* case rather than an accident. The MongoDB path has no equivalent, which
is D4 restated as a code property: **single-tenant MongoDB and multi-tenant PostgreSQL are two
deployment targets over one core, and this is one of the places the core is not yet shared.**

## 4. One deliberate hit, reported rather than excluded

`lib/storage/tenant-scope.js` carries a module-scope `tenancyMode`, and the audit flags it. That
is correct and it stays: the AsyncLocalStorage context it guards is process-wide, so the mode
that decides how to read it has to be too. It is listed here rather than suppressed, because a
census with a quiet exception list is a census nobody can check.

## 4a. Correction — the tool could not see the widest singleton in the tree

**Found by T3.3, which is exactly what the "two holes" section below was for.** The first
version of this tool classified `require('x')()` as a require and excluded it. That is wrong:
`require(x)` is a require, but **`require(x)()` is a factory invocation** — the module hands back
a builder and the call site holds the one instance it built.

`lib/server/server.js:34` is precisely that shape:

```js
const language = require('../language')();      // one per process
const translate = language.set(env.settings.language).translate;
```

So the **single largest-blast-radius singleton in the server was the one the audit could not
see**, and it was absent from the report entirely. `lib/server/server.js:33`'s `env` was hidden
the same way. Both are now reported as a distinct `factory-binding` kind — kept separate from an
ordinary mutable binding because the tool genuinely cannot tell whether a call returns something
frozen, so the reader should weigh it rather than be told.

Revised counts:

| residency | files | bindings | **factories** | writes |
|---|---:|---:|---:|---:|
| **server** | 21 | 32 | **9** | 72 |
| **both** | 15 | 27 | 2 | 7 |
| browser | 40 | 91 | 8 | 152 |

**The second hole T3.3 named is not fixed**: a property written onto a *required module* from
another file. `lib/server/bootevent.js:212` does `ctx.levels.translate = ctx.language.translate`,
mutating `lib/levels.js`'s exported object from outside it. `lib/levels.js` appears in the report
but not among the server-resident six, because nothing *inside it* writes to module scope. A
tool that walks one file at a time cannot see this; it needs a cross-file pass over assignments
whose target resolves to a required module.

## 5. Two holes in the measurement, stated

- **Static, relative `require()` and `import` only.** A dynamic require, or a module reached
  only through a package name, is invisible. This makes the server set a **lower bound** — which
  is the wrong direction for safety, since an unreached server module would be reported as
  browser-only and therefore harmless. Worth re-running against a dynamic-require sweep before
  the lint rule of §5.2 item 4 is written.
- **It finds state, not sharing.** A module-scope binding written only during load is
  configuration; one written per request is state. The `assignment` count separates those two
  cases better than the binding count does, but neither proves a value derived from one tenant's
  request is readable by another's. The two findings in §2 and §3 were confirmed by running
  them, not by counting them — **and that is the standard the rest of the list should be held
  to before anything is called safe.**
