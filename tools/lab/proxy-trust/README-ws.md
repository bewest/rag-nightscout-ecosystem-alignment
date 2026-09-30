# proxy-trust lab: socket.io (WebSocket) cells on the AR chain

This is an add-on to [`ar_chain.sh`](README-ar-chain.md). The only change to
existing lab files is a source guard in `ar_chain.sh` (`AR_SOURCED=1`), so this
runner can reuse the AR containers and `ar_up`.

It fills a gap listed under "Not covered" in `README-ar-chain.md`: WebSocket
upgrades.

> Not medical advice. This is contributor-facing infrastructure documentation,
> and it follows the same disclosure rule as `README.md` (mechanism, not recipe).

## Why sockets need their own cells

Nightscout's socket server resolves the client address of `socket.request`, the
socket.io handshake request. It uses the same helper as HTTP: `forwarded-for`
on 15.0.x and dev, and `lib/server/client-ip.js` on #8754. A socket
`authorize` event with a wrong secret goes through `authorization.resolve()`.
That makes it subject to the same failed-auth delay as HTTP, and it produces
the same admin-notify that the lab reads back. Three things could still differ
from HTTP:

- **The handshake request depends on the transport.**
  - With `polling` then `websocket` (socket.io's default, used by native
    clients), it is the first long-poll GET.
  - **The Nightscout web client never upgrades.** `lib/client/index.js`
    connects both the main and the `/alarm` namespaces with
    `transports: ["polling"]` (15.0.5 through dev `7000eb18`). So every browser
    socket, including alarm acks, is a series of HTTP long-polls through
    every hop. The `polling` cells in W1, W2 and W3 are the browser's case.
  - With `websocket` alone, it is the Upgrade request.
- **A hop can pass HTTP but break the upgrade.** It might drop `Upgrade` or
  `Connection`, or not speak HTTP/1.1 upstream. When that happens, the client
  quietly stays on polling. Any "the socket path is fine" result then describes
  polling, not WebSocket.
- **Upgraded and long-poll connections stay open.** Hop timeouts that are
  harmless for REST requests can cut them off.

## Cells

| cell | question | how we know it's not vacuous |
|---|---|---|
| **W0 upgrade** | Does the socket end on the transport asked for? With `websocket` in the list: on `websocket`, with a `101` logged at every HTTP hop. With `polling` alone: on polling, never upgraded. | This is the precondition for W1 and W2. The selftest control shows that a plain GET logs no `101`. |
| **W1 address** | Which address is recorded for a wrong-secret socket `authorize`? Is it the honest client? Does a wrong-secret HTTP request from the same client record the **same** address? | The cell fails with `(no notify)` if nothing was recorded. |
| **W2 adversarial** | Each header family from the private probes set in the socket handshake. Tracked output says protected / not protected only. | A probe that ended on a transport other than the one asked for, or that the polling transport can't send (XHR-forbidden header), counts as `vacuous`, not `protected`. |
| **W3 idle** (off by default) | A socket left idle, with `proxy_read_timeout` and `proxy_send_timeout` set to N on every HTTP hop. How many disconnects happen in the window? | `default` means no directive (nginx's 60s). The requested and final transports are both reported. |

The client is a `node:22-alpine` container at `172.31.66.14`. It uses
socket.io-client from the PR tree's `node_modules` (4.8.3 in both trees),
mounted read-only. A custom DNS lookup maps each public name to the lab's entry
address, so `Host` is real on both transports; XHR polling can't override
`Host`.

## Running

The environment is the same as for `ar_chain.sh`:

```
PROXYLAB_STATE=/outside/git ./ws_chain.sh selftest     # no Nightscout: upgrade + headers per hop (27 checks)
PROXYLAB_STATE=… DEV_TREE=… PR_TREE=… ./ws_chain.sh run                       # W0 + W1
PROXYLAB_PRIVATE_PROBES=… PROXYLAB_PRIVATE_RESULTS=… ./ws_chain.sh o2families # W2
WS_IDLE=1 WS_IDLE_TIMEOUTS="10 20 24 26 30 default" ./ws_chain.sh idle       # W3
```

Knobs:
- `WS_TOPOS`, `WS_SETTINGS` and `WS_TRANSPORTS` pick a subset of cells.
  `WS_TRANSPORTS` defaults to `polling polling,websocket websocket`.
- `WS_IDLE_TOPO` (default `AR-PP2`), `WS_IDLE_MS` (default 90000) and
  `WS_IDLE_TRANSPORTS` (default `websocket polling`) control W3.

W3 rewrites the rendered hop configs in place and reloads nginx, then puts the
originals back.

## Results

Measured 2026-09-30 on the 15.0.9 candidate: dev `7000eb18` (#8754, #8765 and
BF-80 merged) at every setting, and 15.0.8 `92d08342` unset. socket.io 4.8.3 on
both ends; three transports (`polling`, `polling,websocket`, `websocket`).
Files:

- `results/matrix-ws-2026-09-30.md` (W0, W1);
- `results/o2-families-ws-2026-09-30.md` (W2);
- `results/ws-idle-2026-09-30.md` (W3).

**Selftest: 27/27 checks pass.** The upgrade reaches the backend with
`Upgrade: websocket` and `Connection: upgrade` in all four shapes. The
forwarded `X-Forwarded-For` on the upgrade equals the honest HTTP chain. Every
HTTP hop logs a `101`. The plain-GET control reaches the backend without being
upgraded and logs no `101`.

**W0 + W1: 96/96 cells.**
- Every cell ended on the transport asked for: the two upgrade transports on
  `websocket` with a `101` at every hop, polling-only on polling.
- In every cell, the address recorded for the socket was the same as for HTTP
  from the same client.
- The `polling,websocket` and `websocket` grids are identical, cell for cell,
  to the 2026-09-28 run on #8754 `81623f9b`. The `polling` grid (the web
  client's case, not measured before) gives the same addresses.
- So the socket path has no address logic of its own on the candidate either,
  and the `TRUST_PROXY` deployment matrix applies to sockets as it stands.
  `AR-L4` resolves the L4 box or a proxy at every setting, as it does for HTTP.

**W2: 24 rows, 120 probes, none vacuous.**
- Unset is **not protected** on all four shapes and all three transports; the
  expected count is protected on all of them.
- It matches `results/o2-families-ar-2026-09-24.md` (HTTP) row for row.

**W3: idle socket vs hop timeouts.** `AR-PP2`, `TRUST_PROXY=2`, 90s idle.
The same counts on `7000eb18` as on 2026-09-28:

| hop timeout | drops in 90s (websocket = polling) |
|---|---|
| 10s | 8 |
| 20s | 4 |
| 24s | 3 |
| 26s, 30s, default (60s) | 0 |

- The edge is socket.io's ping interval (25s; Nightscout doesn't change it).
  An idle connection carries nothing but the server's ping, so any hop whose
  read or send timeout is below 25s cuts it on every cycle.
- The client reconnects each time (it was connected at the end in every
  cell). The cost is a fresh handshake, `authorize` and data load on each
  drop, not an outage.
- Long-polling hits the same edge, because the server holds each poll open
  for up to one ping interval.
- **The tradeoff:**
  - Below 25s, sockets churn.
  - Just above 25s holds in the lab, but only by the lab's near-zero latency.
  - Well above it (nginx's 60s default) costs only idle file descriptors held
    longer on a dead peer. socket.io's own ping timeout detects a dead peer
    in about 45s whatever the hop allows.
  - Set every hop, and any LB idle timeout, **comfortably above 25s**. 60s is
    the measured-safe default.


### Earlier run

2026-09-28, dev `f1591069` unset and #8754 `81623f9b` before it merged, two
transports: selftest 27/27, W0+W1 64/64, W2 16 rows and 80 probes, W3 as
above. Files `results/*-ws-2026-09-28.*`. The 2026-09-30 run repeats it on the
candidate after #8765 moved every client-address consumer onto one
`TRUST_PROXY` policy and BF-80 changed the alarm socket's delay.

## Not covered here

- **Cloud LB behaviour.** A local lab can't reproduce these; they have to be
  measured against the real LB:
  - backend keepalive combined with PROXY protocol on an L7 rule. If the LB
    reuses one backend connection for several clients, a PROXY header sent
    once per connection names the wrong client;
  - LB idle timeouts;
  - health checks against a `proxy_protocol` listen.
- O3/O4 throttle cells over sockets.
- TLS (`wss://`) through the chain.
