# Trusted evaluator scheduling repair: focused source and native qualification

Captured 2026-11-12. **Reproduced** controls and measurements; source repair is
fixed on the local branch. Shipping clinical/Socket.IO composition and the
coordinator's frozen full acceptance remain separate, unmeasured criteria here.
The [original d505 finding](../original/README.md) remains immutable. This record
does not attribute every previously cancelled outbox request to that finding.

## Exact boundary

Joined source: `195c932293f3abc648da8fbe4356bf7360acd002`, branch
`codex/evaluator-job-context-20261112`. Product boundary independently reviewed:
`53a8ad725049e6bdacdd903ea8bd759c64781c8d`; subsequent `f145c341f` and the ordinary
`dfc3e6b8` merge repair recording/cache fixtures only. Native instrument bytes
are unchanged across those joined fixtures. [Source and guard digests](source-and-guard.json)
record the exact history and byte comparison.

The evaluator allocates one authority-free scheduling context for its clinical
runtime and one for selected delivery at boot entry. Boot refuses inherited
tenant or active/expired/closed-window authority. A weak observer registry is
used only for boot; explicit caller admission uses constant-time weak lookups.
The existing `execute()` parent guard is byte-identical. The module file changes
because it adds assertion-only parent observation; it does not detach, clear or
mutate an operation scope.

Due/repeat timers, revision drains, deferred owned checks, feed checks,
membership callbacks and registry activation enter their boot-owned scheduling
boundary. Clinical/configuration/phase admission is obtained afresh for each
owned job. Revision/current-output observation remains in its valid originating
window; producer selection, durable attempt and provider callback remain
awaited inside the delivery window.

Explicit callers preserve active same-tenant reuse, including coalesced acquire,
no-stamp wake, backstop and delivery calls. Borrowed work receives no strict
fresh-owned completion credit. Owned and borrowed work each have two fixed
pending slots per tenant/component. An explicit parent joining independent work
that needs its held client receives `EVALUATOR_JOB_PARENT_BUSY` before queue
mutation. Expired and foreign callers refuse before tenant work is enqueued.

## Measurements and controls

| Instrument | Reproduced result | Scope |
|---|---|---|
| [One coherent affected batch](coherent-affected.txt), [exact 34 files and flags](coherent-files.json) | 266 passing, 56 pending, exit 0 | Native flags unset. Pending opt-ins are not native acceptance. Includes activity, feed, live-add, producer, lifecycle, owner configuration and existing no-window consumers. |
| [Registered native corpus](native-corpus.txt), [runner record](native-corpus.json) | 2 passing, 0 pending, 0 failing | Actual disposable PostgreSQL lifetime and durable outbox, synthetic clinical/suppression ports and controlled accepting adapter. |
| [Scheduling neutrality removed](neutrality-mutant.txt) | 0 passing, 1 failing: `SCHEDULER_PROGRESS_TIMEOUT`; exact bytes restored | Recording lifetime protocol; original expired-parent due failure becomes observable again. |
| [Prior schema over actual UDS](empty-summary-prior-schema-red.txt) | Empty configured roster refuses with `SOCKET_IPC_UNAVAILABLE`; restored [controls](small-controls-restored.txt) pass | v2 schema now admits existing empty registry boot. This is not native empty-role boot evidence. |
| [Prior consumer error path](consumer-prior-error-path-red.txt) | Missing expected activity-port rejection; restored controls pass | Explicit ticket rejects and internal drain rejection is observed. Recovery delivers again. |
| [Shared context fixture mismatch](adjacent-missing-context-fixtures-red.txt) | 177 passing, 2 failures: missing branded contexts; [restored](adjacent-context-fixtures-restored.txt) 179 passing | Recording fixtures now explicitly own and close their contexts; no production fallback. |
| [Tier inventory](tier-inventory.txt), [native inventory](native-inventory.txt) | 705 files / 8 tiers; 85 opt-in suites, new runner selected | New tests are registered in both required inventories. |

The native window pool has **max 1, observed 1 session**. The separate outbox
pool also has **max 1, observed 1 session**; setup/independent observation uses
an admin connection. This is not one PostgreSQL connection total. Before the
adapter accepts, the admin connection independently sees the committed request
in `attempting`; accepted state persists afterwards. The same run observes
revision-triggered delivery, repeat acceptance, no-write time-only completion,
actual direct `window -> await runtime.acquire/wake/backstop` coalescing,
`consumer.wake` coalescing, nested window reuse, independent queued-work busy
refusal followed by owned progress, pause/suspension refusal/reactivation and
late runtime/delivery refusal. The exact owned container and recorded anonymous
volumes are verified absent after teardown. PostgreSQL is pinned to
`postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`.

Private inspection module v2 adds runtime identity and successful acquisition /
time-only completion counters after the fresh owning window resolves, plus
completion age, failure count and never-reused ownership/config/lifecycle
generation. Unchanged signature checks and borrowed/unfinished/invalidated work
receive no successful credit; no-window paths retain legacy cycles and strict
completion counters stay zero. Optional unique selectors contain at most 128
tenants; `[]` is summary only. Selected reads skip whole startup/registry/runtime
and delivery rosters. The selected 128-row DTO measured **50,502 bytes**. Existing
module server 4 MiB and lifecycle-manifest 1 MiB caps remain unchanged; the new
collector uses a 1 MiB client cap. Legacy `{}` remains the bounded whole-view
compatibility request.

## Failed repair and fixture evidence retained

The first repair `5ad00a523` incorrectly detached explicit active-parent calls.
The peer's [coalesced matrix](peer-coalesced-matrix.json) reproduces d505 inline
completion versus 5ad deadlock; an independently queued parent-held-client join
already deadlocks on d505. The later [parent matrix](peer-parent-matrix.json)
reproduces 6e52's acquire/wake and acquire/backstop busy regressions. These are
recording one-client protocols, not PostgreSQL evidence. The final native and
recording matrices preserve those supported inline cases while the distinct
independent join now refuses promptly. No present check-parent deadlock was
attributed to the original clinical scheduling finding.

A [50 ms synthetic repeat fixture failed](native-50ms-fixture-failure.txt).
A [scratch discriminator](native-heartbeat-discriminator.txt) observes the
committed first attempt then repeat behavior with a realistic one-second
synthetic heartbeat. The final fixture uses that heartbeat and a finite 10 s
wait. Product repeat floor, product deadlines and capacity cadence are unchanged.
The failed run is preserved; it is not counted green.

## Reproduction and remaining boundary

In the exact joined core, run the files in `coherent-files.json` with Mocha,
`--timeout 15000`, and native flags unset. The native criterion is selected by:

```bash
node scripts/test-multitenant.js --only evaluator-job-context --record /tmp/evaluator-jobs.json
node scripts/test-tiers.js check
```

All artifact digests are listed in [artifacts.sha256.json](artifacts.sha256.json).
The full affected batch capture omits console error body fields; its private raw
hash and redaction scope are [recorded separately](coherent-public-capture.json).

Coordinator owns final official/dev integration, frozen full/browser/enabled
corpus/prcheck acceptance and deployment SOURCE metadata. A fresh source/image /
binding/state/project tuple must qualify real two-to-three clinical alarm
handoff, stock polling/WebSocket/API3 and restore under continuous B settings
traffic. Retained failed d505 and suspended D8 projects must not be reset or
receive source overlays. Test-only synthetic configuration-authority bootstrap
remains explicitly separate from a shipping owner/operator issuance capability.
