# proxy-trust lab: auth_request chain (AR) topologies

Add-on to this lab (`lab.sh`, `run_matrix.sh`). It does not modify either file.
It covers a shape the F/TLS/L-B topologies do not: a **multi-tenant hosted
platform** where nginx picks the **next hop for each request** from an
`auth_request` subrequest, several times in a row. The shape looks like this:

```
client ─► L4 LB ──PROXY protocol──► GATEWAY ──► ROUTER ──► TENANT ROUTER ──► Nightscout
          (TCP)                     auth_request auth_request auth_request
                                    name→origin  name→tenant  tenant→host:port
```

> Not medical advice. This is contributor-facing infrastructure documentation,
> and it follows the same disclosure rule as `README.md` (mechanism, not recipe).

## Why this shape needs its own cells

- **The hop count changes with the route.** The gateway's authorizer returns
  the upstream origin, so one gateway can send one public name through a
  second router (3 HTTP hops to Nightscout) and another name straight to the
  tenant router (2 hops). A single `TRUST_PROXY` value has to be right for
  every route that reaches the same Nightscout.
- **The edge overwrites X-Forwarded-For.** It does not append. The gateway sets
  `X-Forwarded-For $proxy_protocol_addr` and does not use `real_ip`. Every
  other lab topology appends.
- **The last hop does not set `X-Forwarded-Proto`.** The tenant router leaves
  it out, so the scheme Nightscout sees is whatever the first HTTP hop wrote.
- **The backend comes from a variable.** It is a header from the subrequest
  (`proxy_pass $tenant$request_uri`), so the routing itself is part of what is
  being tested.

## Topologies

The authorizer and resolver are small nginx `127.0.0.1:9000` stub servers
inside each hop's container. Every path ends at the same tenant router (`.93`),
which is the socket peer Nightscout sees.

| id | path (IPs on 172.31.66.0/24) | HTTP hops that set XFF | expected `TRUST_PROXY` |
|---|---|---|---|
| `AR-PP3` | client `.10` → L4+PP `.90` → gateway `.91` (overwrite) → router `.92` → tenant `.93` | 3 | `3` |
| `AR-PP2` | client → L4+PP `.90` → gateway `.91` (overwrite) → tenant `.93` | 2 | `2` |
| `AR-L4` | client → L4 **without** PP `.94` → router `.92` → tenant `.93` | 2 | **none works** (client address lost at L4) |
| `AR-L4PP` | client → L4+PP `.96` → router `.97` (`real_ip_header proxy_protocol`, append) → tenant `.93` | 2 | `2` |

Config files are in `frontends/ar-*.conf`:

- `ar-l4-stream.nginx.conf`: `PP_DIRECTIVE` is either on or empty.
- `ar-gateway.conf`: routes by `Host: <view>.gw.test`. `guest` goes to the
  router, `hosted` goes to the tenant router, and any other name gets 401.
- `ar-router.conf`: `ROUTER_LISTEN` / `ROUTER_REALIP` select the plain variant
  or the PP + real_ip variant.
- `ar-tenant-router.conf`

The gateway has one documented deviation. On a real platform, the internal
Host comes from the hostname in the origin URL. The lab has no DNS, so the stub
returns it in `X-Forwarded-Host`.

## Results, 2026-09-24

The results are in two files, both sanitised:

- `results/matrix-ar-2026-09-24.md` has O1 for every setting, plus a
  **single** chain-injection O2 taken from the private probes. It covers PR
  `81623f9b` and dev `f1591069`.
- `results/o2-families-ar-2026-09-24.md` has O2 across **every** header family
  the compatibility path reads, from `./ar_chain.sh o2families`. **This file is
  the authority on protection.**

**O1: which settings resolve the honest client (`.10`)**

- `AR-PP3`: 3, 4 or `true`.
- `AR-PP2` and `AR-L4PP`: 2, 3, 4 or `true`.
- `AR-L4`: never. Every setting resolves a proxy (`.92`, `.93` or `.94`).
- Lower counts resolve the proxy that far in. For example, `AR-PP3` at 2
  resolves the gateway `.91`.

**O2 across all header families (the authoritative result)**

| topology | unset | expected count |
|---|---|---|
| `AR-PP3` | **not protected** | 3: protected |
| `AR-PP2` | **not protected** | 2: protected |
| `AR-L4` | **not protected** | 2: "protected", but it resolves the L4 box, so every client shares one address |
| `AR-L4PP` | **not protected** | 2: protected |

This means unset is not protected behind any AR shape. That includes the
chains whose edge **overwrites** X-Forwarded-For from PROXY protocol. The
compatibility path reads more than X-Forwarded-For, and the gateway strips only
XFF and X-Real-IP. So the single-injection matrix shows "protected" for unset
on `AR-PP*`, and **that cell overstates protection**. Use the families table.

Unset behaves the same on dev and on PR, in all four shapes, for both O1 and
single-injection O2.

**Settings above the expected count** (single injection only; not re-run
across families):

- `AR-L4PP` is not protected at 3, 4 and `true`. This is the lab's general
  result for an edge that appends.
- `AR-PP*` measured protected at 4 and `true`. With a count or `true`,
  resolution reads X-Forwarded-For only (proxy-addr), and the edge replaces
  XFF. So this rests on *every* route in overwriting at the edge, and on
  nothing reaching an inner hop directly. Neither is guaranteed, so **use the
  exact count**.

**Routing non-vacuity**

- Every cell requires that the chain delivered the request to Nightscout: no
  421, 5xx or timeout from a hop.
- `selftest` shows the gateway answers 401 for an unauthorized name and 421 for
  a foreign Host.
- The Host is rewritten to `tenant1.backends…` at the tenant router.

### How to read this for configuration

- **Set `TRUST_PROXY` to exactly the number of HTTP hops that set
  X-Forwarded-For**, counting from Nightscout out to the first hop that learned
  the real client. PROXY-protocol L4 hops do not count. The measured values are
  `AR-PP3` 3, `AR-PP2` 2, and `AR-L4PP` 2.
- **When routes have different lengths, one value can't be exact for all of
  them.** If one Nightscout is reachable through both a 2-hop and a 3-hop route
  (`AR-PP2` and `AR-PP3`), a single `TRUST_PROXY` over-counts one route or
  under-counts the other. Make the routes the same length, or use an address
  list (the proxy IPs or CIDRs) instead of a count.
- **Unset is never safe behind these chains**, even when the edge replaces XFF.
- **An L4 load balancer without PROXY protocol cannot be fixed with
  `TRUST_PROXY`.** Enable PROXY protocol on the LB *and* have the first HTTP hop
  consume it (`listen … proxy_protocol`) in the same change. If only the LB side
  is switched, every request fails with 400 (see `lb-l2-misconfig-noproxyproto.conf`).

## Running

The environment is the same as for `lab.sh`. The runner starts mongo and the
network itself.

```
# no Nightscout needed: swaps Nightscout for a header-echo backend and asserts
# the peer, XFF, Host rewrite and proto seen at the last hop for an honest
# client (18 checks; no adversarial headers)
PROXYLAB_STATE=/outside/git ./ar_chain.sh selftest

PROXYLAB_STATE=… DEV_TREE=… PR_TREE=… ./ar_chain.sh run      # O1 (+ O2 with probes)
PROXYLAB_PRIVATE_PROBES=…/probes.json … ./ar_chain.sh run    # + single-injection O2
PROXYLAB_PRIVATE_PROBES=… PROXYLAB_PRIVATE_RESULTS=… ./ar_chain.sh o2families  # all header families
AR_SETTINGS="2 3" ./ar_chain.sh run                           # subset of settings
./ar_chain.sh down                                            # stop, do not remove
```

The output JSONL has the same fields as `run_matrix.sh`, plus `expected_tp` and
`o1_correct`. `tools/analyze.py` renders it unchanged, and `run` calls it.

## Not covered here

- The real behaviour of the cloud LB. PROXY protocol, TLS passthrough and XFF
  handling on the provider's L7 port have to be cited from vendor docs.
- TLS/O5 on this chain. The tenant router passes the first hop's
  `X-Forwarded-Proto` through, so O5 should behave as it does in `TLS`, but
  that is unmeasured.
- WebSocket upgrades, and O3/O4 throttle cells.
- Full-family O2 at settings other than unset and the expected count.
- In-cluster callers that bypass the edge and reach the tenant router
  directly, which a hop count would trust.
