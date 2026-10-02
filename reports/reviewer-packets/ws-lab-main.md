<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — WS-LAB

**tools/lab/proxy-trust - socket.io (WebSocket) cells on the AR chain (W0-W3)**

| | |
|---|---|
| repository | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=WS-LAB` is the measurement |
| semver | `n/a` |

## What this changes

tools/lab/proxy-trust/ws_chain.sh, tools/ws_probe.js, tools/ws_echo.js,
tools/ws_analyze.py, README-ws.md, results/*ws*; one source guard (AR_SOURCED)
added to ar_chain.sh.

## Why that semver

programme tooling

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'bash -n tools/lab/proxy-trust/ws_chain.sh && bash -n tools/lab/proxy-trust/ar_chain.sh && node --check `** &nbsp;·&nbsp; kind: `static`

The lab scripts parse. Says nothing about what they measure.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The measurement needs Docker, MongoDB and two Nightscout trees
  (ws_chain.sh selftest/run/o2families/idle), so it is not a queue gate.
  2026-09-30 on dev 7000eb18 (15.0.8 92d08342 unset): selftest 27/27; run
  96/96 cells W0 ok and socket address equal to HTTP over three transports;
  o2families 24 rows, 120 probes, none vacuous; idle 12 cells. 2026-09-28 on
  #8754 81623f9b gave the same grid.

## Evidence

- [`tools/lab/proxy-trust/README-ws.md`](../../tools/lab/proxy-trust/README-ws.md)
- [`tools/lab/proxy-trust/results/matrix-ws-2026-09-30.md`](../../tools/lab/proxy-trust/results/matrix-ws-2026-09-30.md)
- [`tools/lab/proxy-trust/results/o2-families-ws-2026-09-30.md`](../../tools/lab/proxy-trust/results/o2-families-ws-2026-09-30.md)
- [`tools/lab/proxy-trust/results/ws-idle-2026-09-30.md`](../../tools/lab/proxy-trust/results/ws-idle-2026-09-30.md)
- [`tools/lab/proxy-trust/results/matrix-ws-2026-09-28.md`](../../tools/lab/proxy-trust/results/matrix-ws-2026-09-28.md)

## Notes carried on the item

Closes the "WebSocket upgrades" gap listed in README-ar-chain.md. Measured
2026-09-30 on the 15.0.9 candidate, dev 7000eb18 (#8754, #8765 and BF-80
merged), at every TRUST_PROXY setting, with 15.0.8 unset, over polling-only
(the web client's setting), polling-then-upgrade and websocket-only: every
cell ended on the transport asked for, and the address recorded for a wrong-
secret socket authorize equals the HTTP one, so the TRUST_PROXY deployment
matrix applies to sockets unchanged. The upgrade grids are identical to the
2026-09-28 run on #8754 81623f9b. W2 (all header families in the handshake)
matches the HTTP families table row for row: unset not protected everywhere,
the expected count protected. W3 (idle vs hop timeouts, off by default): a hop
timeout below the 25s socket.io ping drops the idle socket every cycle (10s:
8, 20s: 4, 24s: 3 drops in 90s); 26s and above hold. Owed, outside this item:
cloud-LB cells (backend keepalive with PROXY protocol on an L7 rule, LB idle
timeout, health checks) need a real LB; O3/O4 throttle over sockets; wss://
through the chain.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=WS-LAB` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
