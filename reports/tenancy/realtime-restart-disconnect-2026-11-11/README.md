# Realtime: server-side disconnects after a full role restart (read-only diagnosis, 2026-11-11)

*Contributor-facing. A read-only diagnosis: code read plus the counters the capacity instrument already
wrote for run b3. Nothing was run for this record. Every code claim is **read-derived**. Figures marked
**measured (b3)** are copied from the b3 instrument output, not re-measured here.*

**Anchors.**
- Core `workspace/capacity-fixes-20261111` at `5c60aec6`: batch head `0392acf9` plus `5517cb6c`, `12fa221d`
  and `5c60aec6`. The worktree is clean.
- Run b3 at 1,000 tenants used image `nscap:5c60aec6-d1c7aca`, with `realtimeMaxSockets` 2000 from the deploy log.
- Its local run directory is `capacity-5c60-20261111/b3-n1000` under `externals/work/` (untracked).
- The realtime overlay `preview-realtime-stats.js` differs from core `lib/server/serve/preview-realtime.js` only by
  the 1 s `DIAG` line. `realtime-config-stats.js` adds only read timers.

## Verdict

The 499 server-side disconnects fit the **process-wide socket cap**, `lib/server/realtime/protocol.js:352`.
They do not fit an authorization path.

How the cap produces them (read-derived):
- In b3, `maxSockets` was exactly `tenants × 2` = 2000, which equals the number of clients.
- After the restart, the probe clients each opened a second engine session, after the edge restart cut their
  first one.
- Realtime keeps an engine session it has not yet seen die. A polling session is detected only by the engine.io
  ping timeout: `pingInterval` 25 s + `pingTimeout` 20 s in engine.io 6.6.10, `node_modules/engine.io/build/server.js:48-49`.
  So for up to about 45 s, stale sessions (ghosts) count in `states`.
- `states` reached the cap. Each new connection was then accepted at the namespace level, and `bind` answered it
  with `socket.disconnect(true)` (`protocol.js:352`). The client sees `io server disconnect` and stops for good.
- When the ghosts expired, `states` fell to the 1501 live sockets and stayed there.

The authorization paths keep the socket connected and retry on not-ready, timeout and warming. That is the decided
model, already in the code.

## Measured (b3) counters that discriminate

From the realtime `DIAG` line, seconds from the restart command:

| s | sockets in `states` | primed | queued | authorize in flight | `invalidated` | `primeRefreshFailures` | `recheckFailures` |
|---|---|---|---|---|---|---|---|
| 13 | 1116 | 14 | 287 | 810 | 0 | 0 | 0 |
| 22 | 658 | 11 | 275 | 595 | 0 | 0 | 0 |
| 28 | **2000** | 11 | 1045 | 960 | 0 | 0 | 0 |
| 30 | 2000 | 11 | 633 | 1071 | 0 | 0 | 0 |
| 40 | 2000 | 61 | 725 | 744 | 0 | 0 | 0 |
| 50 | 2000 | 119 | 1019 | 518 | 0 | 0 | 14 |
| 52 | 1989 | 133 | 1054 | 469 | 0 | 0 | 14 |
| 54 | 1798 | 130 | 1219 | 346 | 0 | 0 | 14 |
| 56 | **1501** | 131 | 1156 | 240 | 0 | 0 | 14 |
| 70 | 1501 | 211 | 1204 | 54 | 0 | 0 | 14 |

What the client probe recorded (b3 `probe.json` `restart.reasons`):

| reason | count |
|---|---|
| `transport close` (role restart) | 1999 |
| `transport error` | 1975 |
| `connect_error:xhr poll error` | 12023 |
| `connect_error:xhr post error` | 797 |
| `io server disconnect` | 499 |

- The edge restart began at +9.6 s (`edgeRestarted.atMs` 9567) and its command took 11.2 s.
- At the end, 1501 stock clients had recovered. With manual reconnects all 2000 recovered, in 6.3 s.

How to read these counters:
- **Flat at exactly 2000 for about 22 s.** The plateau sits at the configured cap while clients were still
  reconnecting. Refused binds never enter `states` (`protocol.js:352` returns before `states.add` at `:358`), so
  the count cannot rise past the cap.
- **Fall of 499 between +51 and +56 s.** That is about 45 s after the edge restart, the engine.io ghost lifetime.
  Ghost sessions have no client attached, so their expiry produces no client event.
  - The 499 clients the cap refused never come back, so `states` stays at 1501.
  - 2000 − 1501 = 499, which equals the client-side `io server disconnect` count.
- **`invalidated` stays 0.** That rules out three paths that increment it:
  - recheck refusal (`:322`);
  - the no-read retire (`:333`);
  - tenant invalidation (`:456`). This also rules out the activity gate and the change detector, which both reach
    `invalidateTenant`.
- **`primeRefreshFailures` stays 0.** That rules out the prime catch at `:304`.
- **Every remaining retire path covers only primed sockets, except two.** The paths limited to primed sockets are
  fanout (`:427`), alarm (`:439`, `:448`), window invalidation (`:299`) and the recheck paths. `primed` was 11–135
  in the window, so these cannot account for 499 sockets. The two exceptions:
  - bind refusal;
  - `refuse()` for a socket still priming (`:224`, `:240`, `:287`). This needs a refusal code (see Q2), and none
    fits.

What this does not establish:
- The client-side timing of the 499 disconnects. The b3 `probe.json` has no `serverDisconnectsBy5s`, so that field
  was added to the probe after b3.
- The exact source of each ghost: which sessions the edge restart left undetected.

The cap explanation predicts that the client-side disconnects fall between about +28 and +50 s, while `states`
is pinned at 2000. A `refuse()` explanation would put them at +51 to +56 s. See "Confirming controls".

## Q1. Every server-side disconnect in realtime, and its trigger (read-derived)

All in `lib/server/realtime/protocol.js` unless stated.

| site | call | trigger | logged? |
|---|---|---|---|
| `:352` | `socket.disconnect(true)` in `bind` | process closed, **`states.size >= maxSockets`** (all tenants and namespaces, one process-wide limit), or an unknown namespace | no |
| `:353` | same | socket not prepared (the middleware did not run) | no |
| `:357` | same | process closed between checks | no |
| `:374` | same, in the `authorize`/`subscribe` handler | credential shape refused by `credentialFor` (`authority.js:7-21`), or a human-session credential mismatch (`:365`, `:367`) | no |
| `:105` `retire()` via `refuse()` `:206-212` | `disconnect(true)` | an error whose code is in `REFUSALS` (`:23-26`) or a lifecycle suspension (`windows.isSuspension`), raised while priming: `current()` → `admitted()` `:108-110` (admission mismatch or `readCurrent` null → `REALTIME_SOCKET_REFUSED`) or `validRights()` `:111-117` (api answered `{denied:true}` → `REALTIME_CLIENT_DENIED`, malformed rights); `/storage` collection errors `:240`; a refusal from the frame or send `:287`, `:304` | no |
| `:299` | `retire()` for every item in the batch | the operation window invalidates the tenant during the prime's data step | no |
| `:322` | `retire()` | recheck got a refusal code (`counters.invalidated++`) | no |
| `:333` | `retire()` | recheck succeeded but the rights no longer include read (`invalidated++`) | no |
| `:389`, `:392` | `disconnect(true)` | `loadRetro` or a forwarded write whose operation window is invalidated, or whose `withOperation` rejects | no |
| `:427` | `retire()` | any send error during fanout to a primed socket (for example the `REALTIME_SOCKET_REFUSED` at `:422` when read was lost) | no |
| `:439`, `:448` | `retire()` | alarm delivery: no read right, `REALTIME_CLIENT_DENIED` or an epoch change | no |
| `:457` `invalidateTenant` | `disconnect(true)` on every socket of the tenant (`invalidated++`) | called from three places: the change detector when a tenant leaves admission or is ineligible (`change-detector.js:55-60`, wired at `preview-realtime.js:96`); the activity gate (`tenant-activity/serving.js:37`, wired at `preview-realtime.js:65-67`); the role's `invalidateTenant` (`preview-realtime.js:109`) | no |
| `socket-server.js:150` | `io.close()` | shutdown. It closes transports, not sockets (the BF-233 fix), so the client reconnects | n/a |
| `socket-server.js:139`, `:143` | handshake refusal | `allowRequest` (engine-level: origin or admission) and namespace middleware (`prepare`) refusal. These are not disconnects of a connected socket, but they differ in how a client retries (Q5) | no |

Not in the list, because they never disconnect:
- An api that is not ready, has timed out or is warming during authorize. The transport client raises
  `SOCKET_IPC_UNAVAILABLE` with no `code` (`internal-api/transport.js:39`, `:328`, `:340-352`), so `refused()` is
  false and the item is retried (`protocol.js:224`, backoff `:182-188`).
- A recheck that cannot reach the api: the socket is held (`:322`).
- A tenant that is cold or warming in realtime: the socket is parked (`:253-262`).

## Q2. Which path fits

**The cap at `:352` fits.** The mechanism and the counters are above.

**Authorize during the api restart does not disconnect (read-derived):**
- On the api side, `authorizeSocket` calls `prepareTenant` (`private-api.js:71`), which is `startup.admit`
  (`preview-api.js:127`, `:136`). For a cold tenant that throws `TENANT_WARMING` (`tenant-startup.js:191-192`).
- The internal handler answers `TENANT_WARMING` with the not-ready 503 body (`transport.js:36`, `:187`). For a
  tenant that failed recently, `TENANT_UNAVAILABLE` (`tenant-startup.js:188-190`) gets the opaque 503.
- Either way the realtime client rejects with a codeless `SOCKET_IPC_UNAVAILABLE` (`transport.js:340-344`). A
  timeout or connection reset rejects the same way (`:347-352`). `refused()` is false for both, so the socket stays
  connected, unprimed, and is retried per tenant with backoff from 250 ms to 5 s (`protocol.js:20`, `:182-188`).
- Only a 200 `{denied:true}` reaches a refusal. The api returns it only for a credential-class error
  (`private-api.js:74-76`), and for the probe's exchanged JWT those are deterministic. b3's prime phase, before the
  restart, primed 2000/2000 with 0 server disconnects (measured (b3) `probe.prime`).

**A socket that connected while its tenant was cold or warming is not disconnected when a later authorize or
recheck fails or times out (read-derived):**
- A prime failure that carries no refusal code goes to `retryable` (`:224`, `:304`).
- A cold tenant parks the socket and wakes the runtime (`:257-262`), and `tenantReady` releases it (`:462-467`).
- A recheck reaches only sockets that are primed and hold rights (`:314-315`). A non-refusal failure sets
  `held = true` (`:322`): the socket stays connected, fanout skips it and marks `missed` (`:415`), and the next
  successful recheck resends (`:326`, `:334-337`).

**What `recheckFailures` counts:** recheck attempts on primed sockets that failed without a refusal code
(`:322`). The effect is a hold, never a disconnect.
- The periodic sweep runs every `authorizationRecheckMs`, 30000 in b3, over 8 tenants at a time (`:19`,
  `:341-350`).
- The 14 in b3 are primed sockets whose first sweep, at about +42 s, met the restarting api. They were held, not
  disconnected.
- Side note (read-derived): a held socket's frames resume only after a later recheck succeeds, so a viewer can go
  up to one sweep interval without frames.

**The warm retry covers only realtime's own warm.**
- `tenant-startup.notReadyRetry` wraps only the startup initializer's probe `authorizeSocket`
  (`preview-realtime.js:73`, `:82`).
- Socket-connect authorization goes through `protocol.js:126` with no `notReadyRetry`. It does not need one: the
  priming queue already retries without disconnecting. Its backoff, however, is per tenant and has no deadline and
  no global bound (Q3).

## Q3. Authorize concurrency (read-derived)

There is no process-wide bound on authorize calls from realtime to the api. Calls are bounded per tenant:
- Each tenant has one priming queue with at most one drain running (`:171-180`, `:189-205`).
- A drain makes one call per distinct `(namespace, host, credential)` in its batch (`authorities()`, `:118-131`).
- In-flight calls are therefore about one per tenant with pending sockets, times the distinct credentials in that
  batch. To that add:
  - the recheck sweep: 8 tenants at a time (`:347`);
  - realtime's own warm: `NS_TENANT_STARTUP_CONCURRENCY` slots (`preview-realtime.js:74`; `tenant-startup.js:142-147`).
- With 1,000 tenants that is about 1,000. The observed values (measured (b3)): 1071 at +30 s, maximum 1082.
- Each call opens its own HTTP connection (`agent: false`, `transport.js:331`).

Two further effects (read-derived):
- During the api's warm, every one of those calls is answered `TENANT_WARMING`.
- Each such call also moves its tenant to the front of the api's warm queue (`tenant-startup.js:191`). With about
  1,000 tenants doing this every 0.25–5 s, front-of-queue becomes close to arbitrary order.
- This is not a disconnect path. It is load: `primeRetries` reached 8477 by +60 s (measured (b3)).
- Realtime CPU was about one core saturated through the first 30 s: 31.7 s user CPU at +30 s, measured (b3).
  A saturated loop delays polling responses and pings, which lengthens the ghost window. That link is read-derived.

## Q4. Single site (read-derived)

A single-site Nightscout has no equivalent window:
- The listener opens only after boot completes (`lib/server/server.js:54-60`).
- Authorization storage is loaded during boot (`lib/server/bootevent.js:269-283`).
- Socket authorization is answered in process (`lib/authorization/index.js:156-246`). There is no peer that can be
  not ready.
- There is no socket cap.

Server-side disconnects on a single site:

| site | trigger | logged |
|---|---|---|
| `websocket.js:138` and `:211` | `humanSocket.select` throws | no |
| `websocket.js:221-224` | authorization error, which in practice means wrong credentials (`authorization/index.js:235-244`, "All validation failed") | yes, `Websocket authorization failed:` |
| `websocket.js:78-82` | shutdown (`teardown`) | not applicable |

The shutdown loop calls `Object.keys(io.sockets.sockets)`, but in socket.io 4.8.3 `sockets` is a `Map`
(`node_modules/socket.io/dist/namespace.js:78`). The loop therefore disconnects nothing, and `io.close()` closes the
transports, so clients reconnect. That is read-derived; BF-233 records single-site shutdown as not checked.

**Conclusion:** after a restart, a single site never disconnects a connected socket from the server side, except
for a genuine credential failure.

## Q5. Candidate fixes, ranked against the 16.0.0 decisions

Decisions consulted (`releases/cgm-remote-monitor-16.0.0/decisions.md`):
- [cost-proportional-to-activity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md) row 498, item (2):
  "the initial frame queued under pool pressure instead of a server disconnect".
- readiness-serve-then-warm, row 501: a tenant that is not warm answers 503 with `Retry-After`, for that tenant
  only.
- incremental-refresh, rows 504 and 506: not touched by these candidates.
- BF-233: a server-side disconnect leaves stock clients dark, and the fix is to close transports instead.

Read together, these say: never answer a transient condition with a server disconnect, and make every refusal one
the stock client retries.

**Client behaviour these rest on.** socket.io-client 4.8.3 in `node_modules`, read-derived:
- `io server disconnect` destroys the socket with no reconnect (`socket.io-client/build/cjs/socket.js:640-642`).
- A namespace-middleware refusal (`CONNECT_ERROR`) also destroys it with no reconnect (`:522-527`).
- An engine-handshake refusal (`allowRequest` → HTTP 403) is an open error. The Manager retries it with its backoff.
  b3's 12023 `connect_error:xhr poll error` are clients doing exactly that and recovering (measured (b3)).
- engine.io calls `allowRequest` only on the handshake, never on later polls (`engine.io/build/server.js:128-172`).

### 1. Refuse at capacity at the engine handshake, retryably (top candidate)

- **Mechanism.** Move the capacity check from `bind` (`protocol.js:352`) into `allowRequest`
  (`socket-server.js:137-140`). The count can be `io.engine.clientsCount` or the protocol's `states.size`, with the
  limit on engine sessions or on bindings. Keep a check in `bind` as a backstop, but make it unreachable in
  practice. One engine session carries up to three namespaces, so the limit's unit needs a decision: the deploy
  derivation counts namespace bindings.
- **What a stock client sees.** A failed connect. It retries with its own backoff, up to 5 s by default, and gets
  in once ghosts expire or capacity frees. It is never permanently dark.
- **Risk.**
  - A full process now makes clients poll the handshake every few seconds. That is cheap: no protocol state and no
    api call.
  - Ghosts still occupy capacity for up to about 45 s.
  - A namespace-middleware refusal is not a substitute, because it also leaves the stock client dark.
  - It does not by itself reduce ghost lifetime. Pair it with candidate 3's cause code.
- **Fit.** Direct. It extends decision (2) and BF-233 to the cap.

### 2. Size the cap with headroom for reconnect overlap (deploy-side, pairs with 1)

- **Mechanism.** `maxSockets = max(100, tenants × per-tenant)` (deploy commit `5b222d9d4` record) leaves no room
  for the up-to-45 s overlap of a ghost and its replacement after any edge or network blip. Add a headroom factor
  in the deploy derivation. An alternative is to shorten engine.io `pingInterval`/`pingTimeout` in
  `socket-server.js:136`, which costs more pings per idle viewer.
- **What a stock client sees.** No refusal in the restart case.
- **Risk.**
  - It only moves the threshold: without candidate 1, an over-cap event still leaves clients dark.
  - Shorter pings add steady-state traffic proportional to viewers. That is consistent with
    cost-proportional-to-activity, but unmeasured.
- **Fit.** Good as a complement, not a fix alone.

### 3. A cause code for every server-side disconnect (do it regardless)

- **Mechanism.** Route every `disconnect(true)` in Q1 through one function that counts and logs a stable code:
  - `REALTIME_SOCKETS_AT_CAPACITY`;
  - the refusal code that `refuse()` received;
  - `WINDOW_INVALIDATED`;
  - `TENANT_INVALIDATED` with its source;
  - `FANOUT_SEND_FAILED`, and so on.

  Expose per-code counters in `stats()`. Log only the code, the tenant and the namespace: never credentials,
  frames or socket ids that could identify a viewer.
- **What a stock client sees.** No change.
- **Risk.** Log volume during a mass event. Rate-limit it, or log counters once per interval.
- **Fit.** Neutral to the decisions. It is what would have made this diagnosis measured rather than inferred, and
  it is the control instrument for candidate 1.

### 4. Bound authorize concurrency process-wide

- **Mechanism.** A semaphore around `api.authorizeSocket` in `authorities()` (`protocol.js:126`), shared by
  priming, recheck and alarm. Optionally add a short-lived per-tenant "api not ready" latch, so a tenant's queue
  waits for the api's `Retry-After` instead of retrying every 0.25–5 s.
- **What a stock client sees.** No disconnect change. First frames may arrive later or sooner depending on api
  contention (unmeasured).
- **Risk.**
  - Head-of-line blocking: authorizations for warm tenants must not queue behind cold ones. Give recheck its own
    share so revocation latency stays bounded.
  - It does not address the observed disconnects.
- **Fit.** Matches readiness-serve-then-warm (bounded warm, a 503 per tenant) and cost-proportional-to-activity.
  The b3 api warm took 111.5 s against 24.5 s at first boot (measured (b3)). Whether retry pressure contributes to
  that is unmeasured.

### 5. Keep the socket and retry authorization on not-ready, timeout or warming

**Already the behaviour** (`protocol.js:21-26`, `:224`, `:304`, `:322`), as decision (2) requires. No change is
needed. The b3 counters do not implicate it.

### Is keeping an unauthorized socket open acceptable?

Yes, under conditions the current code already meets (read-derived):
1. **Nothing tenant-scoped is sent before rights for the current revision.**
   - Fanout skips unprimed sockets (`:414`).
   - `connected`, `dataUpdate` and `clients` are sent only after `validRights` (`:247-286`).
   - The revision/epoch checks (`:100-102`, `:219`, `:229`) drop answers that belong to an earlier credential.
2. **Writes from an unprimed socket are authorized per operation at the api** (forwarder `:391-405` →
   `executeSocketMutation`). The tenant is also checked again in `contextForSocket` (`:393-398`).
3. **A refusal still ends the socket** (`refuse()`).
4. **The number of such sockets is bounded** by the cap, behind the origin and admission handshake checks.

What is not acceptable:
- sending any frame or count before authorization;
- treating a denial as retryable.

A residual to track (read-derived): a client that never authorizes can hold a slot indefinitely, as on a single
site. Any idle deadline added for it must not fire while the api is not ready, or it reintroduces this defect.

## Top two

1. **Refuse at capacity in `allowRequest`, not in `bind`** (`protocol.js:352` → `socket-server.js:137-140`). This
   makes the cap a refusal the stock client retries.
2. **A cause code and counter for every server-side disconnect.** These are the sites in Q1, starting with
   `protocol.js:352`, `:105`/`:211`, `:299`, `:427` and `:457`. They are the instrument that confirms 1.

Size the cap with reconnect headroom in the deploy lane alongside 1.

## Confirming controls (proposed, not run)

- **Control A.** Repeat b3 at `maxSockets` 25000, as b1 did. b1 had 0 server disconnects at 25000 (measured (b1)
  `restart.reasons`), but b1 differs in core head and has no `DIAG` socket timeline. Prediction: 0
  `io server disconnect`, and `states` peaks above 2000 before ghosts expire.
- **Control B.** Repeat b3 unchanged with the probe's newer `serverDisconnectsBy5s`. Prediction: disconnects fall
  between +28 and +50 s. A cluster at +51 to +56 s instead would refute the cap and point at `refuse()`.
- **Control C, after candidate 1.** At `maxSockets` 2000, stock clients recover 2000/2000, and the cause-code
  counter shows `REALTIME_SOCKETS_AT_CAPACITY` refusals at the handshake with 0 `io server disconnect`.
  - Break it: restore the `bind`-side refusal, and `io server disconnect` returns.
