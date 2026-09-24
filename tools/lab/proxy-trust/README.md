# proxy-trust lab

Measures how Nightscout (cgm-remote-monitor) resolves the **client address**
(`lib/server/client-ip.js` / `getRemoteIP`) and how the **failed-login delay**
(`lib/authorization/delaylist.js`) behaves, behind real proxy software and real
sockets, under each `TRUST_PROXY` setting. Built for PR
[nightscout/cgm-remote-monitor#8754](https://github.com/nightscout/cgm-remote-monitor/pull/8754)
(branch `bf2/auth-hardening`).

All numbers here were reproduced live on **2026-09-24** against:

| tree | branch | SHA |
|---|---|---|
| dev baseline | `dev` | `f1591069` |
| PR (TRUST_PROXY) | `bf2/auth-hardening` | `81623f9b` (PR head `280eccbe` is this + a dev merge; `lib/server/client-ip.js` is byte-identical) |
| delay-order revert (O4b; O2 across all header families) | `bf2/auth-delay-dev-order` | `f6f361b1` (`lib/server/client-ip.js` identical to `81623f9b` and unchanged at `607d51b0`) |

> Not medical advice. This is contributor-facing infrastructure documentation.

## What TRUST_PROXY does (from the code under test)

`lib/server/client-ip.js` compiles `TRUST_PROXY` into how the address is resolved:

- **unset / empty (default = compatibility):** address comes from the
  `forwarded-for` npm package exactly as `dev` does today. It reads several
  header families and takes the **left-most** entry. This is header-derived with
  **no proxy trust boundary**.
- **`false`:** socket peer only (ignores all forwarding headers).
- **integer `n`:** Express hop count — trust the `n` proxies closest to
  Nightscout; the address is the entry the `n`-th proxy saw.
- **IP / CIDR list:** proxy-addr, trusting only those proxy addresses.
- **`true`:** Express trust-all — the left-most entry.

The failed-auth delay keys on the **resolved address** and on a salted hash of
the credential (`AUTH_FAIL_DELAY` ms, default 5000). It is therefore only as
good as the address, which is only as good as `TRUST_PROXY`.

## Topology

A docker bridge network `s66lab-net` (`172.31.66.0/24`). **Nightscout runs on the
host, bound to the network gateway** `172.31.66.1:3866`, so containers reach it
and present distinct fixed source addresses. Front ends and clients are
containers with fixed IPs. Mongo is our own `mongo:7`.

| role | address |
|---|---|
| Nightscout (host, on gateway) | `172.31.66.1:3866` |
| honest client / guesser | `172.31.66.10` |
| bystander (different real IP) | `172.31.66.12` |
| F1 nginx append | `.20` · F2 nginx replace `.21` |
| F3 two-hop front `.30` / inner `.31` | |
| F4 Caddy `.40` · F5 Traefik `.50` · F6 HAProxy `.60` · TLS `.70` | |
| L-B front (stream) `.80` / ingress `.81` / inner `.82` | |

Images (pinned; digests recorded in `results/`): `nginx:1.27-alpine`,
`caddy:2.8`, `traefik:v3.1`, `haproxy:3.0`, `curlimages/curl:8.11.1`, `mongo:7`.

## Observables

- **O1** resolved address for an honest client (correct = the client's own IP).
- **O2** whether a caller-supplied forwarding header changes the resolved address.
- **O3** whether a guesser varying both credential and forwarding header is throttled.
- **O4a** a bystander at a different real IP with the correct secret is not delayed
  while the guesser is throttled.
- **O4b** a legitimate client at the **same** real IP as the guesser.
- **O5** over TLS termination the site loads (200) with no redirect loop.

The observation channel is the admin-notify a failed auth emits — *"A device at
IP address %1 attempted authenticating ..."* — read back through the
`adminnotifies` API with the admin secret. Every cell **reboots Nightscout
first** (notifies start empty) and the read is liveness-checked in the same run.

## Named scenarios

- **L-A — single reverse proxy** (the common case): F1 (append) / F2 (replace).
- **L-B — DigitalOcean-style LB + DOKS ingress chain**: an L4 front in TCP mode
  with **PROXY protocol** (nginx `stream{}` + `proxy_protocol on`) → ingress-nginx
  emulation (`listen ... proxy_protocol; set_real_ip_from …; real_ip_header
  proxy_protocol`) → a further in-cluster nginx hop → Nightscout. The DO LB passes
  the client address in the PROXY protocol header and does **not** send
  X-Forwarded-For. (DO's *HTTP* mode reportedly adds X-Forwarded-For; that is a
  separate variant. **The actual DigitalOcean/DOKS behaviour is for the docs
  agent to cite from vendor docs — the lab only proves the local emulation.**)

---

## Per-front-end default X-Forwarded-For behaviour (key output)

**What protects the address is the `TRUST_PROXY` setting, not the proxy.** When a
trusted proxy or load balancer adds its entry to a value the caller may have
supplied, setting `TRUST_PROXY` to the hop count of that trusted proxy is what makes
the difference: Nightscout then reads the entry the trusted hop added and ignores
everything to its left.

The middle column is proxy behaviour: what each proxy does, out of the box, with a
**client-supplied** X-Forwarded-For. The right-hand column is the measured O2 result
with `TRUST_PROXY` unset, across every client-address header family the
compatibility mode reads (see [O2 across all header families](#o2-across-all-header-families)).

| front end | default XFF handling | compat default (`TRUST_PROXY` unset) | right setting |
|---|---|---|---|
| F0 direct (no proxy) | — | **not protected** | `false` → protected |
| F1 nginx `$proxy_add_x_forwarded_for` | **appends** (keeps client's, adds peer) | **not protected** | `1` → protected |
| F2 nginx `$remote_addr` | **replaces** | **not protected** | `1` → protected |
| F3 two nginx hops, both appending | **appends** at each hop | **not protected** | `2` → protected |
| F4 Caddy `reverse_proxy` | **overwrites** (does not trust client XFF by default) | **not protected** | `1` → protected |
| F5 Traefik (no `trustedIPs`) | **strips untrusted / sets its own** | **not protected** | `1` → protected |
| F6 HAProxy `option forwardfor` | **appends** | **not protected** | `1` → protected |
| TLS nginx (terminates TLS, appends) | **appends** | **not protected** | `1` → protected |
| L-B L4 PROXY-protocol front → ingress → inner hop | the L4 front is not an XFF hop (carries the client in the PROXY header); ingress and inner hop append | **not protected** | `2` → protected |

**Consequence:** under the compatibility default no front end in this lab is
protected, whether it appends or replaces X-Forwarded-For. Replacing X-Forwarded-For
at the edge does not make the unset default protected. The fix in every topology is
to set `TRUST_PROXY`: `false` with nothing in front, otherwise the number of
X-Forwarded-For-appending HTTP proxies from Nightscout back to the trusted edge.

> `results/matrix-2026-09-24.md` records O2 with X-Forwarded-For probes only, where
> F2, F4 and F5 hold under unset. That is not the complete O2; the all-families
> result is `results/o2-families-2026-09-24.md`.

## Results — three states per topology

`observed` uses lab addresses: client `172.31.66.10`; F1 peer `.20`; F3 inner
`.31`; L-B ingress `.81`, inner `.82`. "throttle bypassable" means O2 = not
protected (a caller can forge the address the delay is keyed on). Adversarial
recipes are **not** in this repo (see the private results directory).

O2 in these tables: for **unset** and for the **right setting** of each topology it is
the all-families result (`o2_families.sh`, tree `f6f361b1`); for every other setting it
is the X-Forwarded-For run (`run_matrix.sh`, tree `81623f9b`, same
`lib/server/client-ip.js`). Explicit settings read only X-Forwarded-For
(`lib/server/client-ip.js`, `proxy-addr`), so for them the X-Forwarded-For run is the
whole header surface.

### L-A — single nginx reverse proxy

| state | config | observed (O1 / O2) | symptom an operator sees | fix |
|---|---|---|---|---|
| **Working** | append edge, `TRUST_PROXY=1` | `.10` / protected | correct client IP; throttle holds | — |
| Misconfigured | append edge, **unset** | `.10` / **not protected** | admin notice shows a client IP, but a guesser is never throttled | set `TRUST_PROXY=1` |
| Misconfigured | append edge, `TRUST_PROXY=2` (one too many) | `.10` / **not protected** | looks correct for honest users; throttle silently bypassable | set `TRUST_PROXY=1` |
| Misconfigured | append edge, `TRUST_PROXY=false` | **`.20`** / protected | every client collapses to the proxy's IP → everyone throttled together | set `TRUST_PROXY=1` |
| Misconfigured | append edge, wrong proxy IP | **`.20`** / protected | as above (peer address) | set `TRUST_PROXY=1` (or the real proxy IP) |
| **Fixed** | change the above to `TRUST_PROXY=1` | `.10` / protected | correct client IP; throttle holds | — |
| (variant) | **replace** edge (`$remote_addr`), unset | `.10` / **not protected** | admin notice shows a client IP, but a guesser is never throttled; replacing X-Forwarded-For does not make the unset default protected | set `TRUST_PROXY=1` |

### Direct (F0, no proxy)

| state | config | observed | symptom | fix |
|---|---|---|---|---|
| **Working** | `TRUST_PROXY=false` | `.10` / protected | correct client IP; throttle holds | — |
| Misconfigured | **unset** | `.10` / **not protected** | a direct client can still forge XFF and bypass the throttle | `TRUST_PROXY=false` |
| Misconfigured | `TRUST_PROXY=1` | `.10` / **not protected** | trusts a header no proxy set | `TRUST_PROXY=false` |

### F3 — two appending hops

| state | config | observed | symptom | fix |
|---|---|---|---|---|
| **Working** | `TRUST_PROXY=2` (= hop count) | `.10` / protected | correct client IP | — |
| Misconfigured | `TRUST_PROXY=1` (too low) | **`.30`** / protected | admin notice shows the **inner proxy** address, not the client | `TRUST_PROXY=2` |
| Misconfigured | `TRUST_PROXY=3` (too high) | `.10` / **not protected** | looks correct; throttle bypassable | `TRUST_PROXY=2` |
| Misconfigured | unset / false / wrong IP | `.10` bypassable / `.31` peer | bypassable, or collapses to the inner proxy | `TRUST_PROXY=2` |

### L-B — DO-LB (PROXY protocol) + ingress + inner hop

In-cluster XFF-appending hops = **2** (ingress `.81` + inner `.82`). The L4
PROXY-protocol front is **not** an XFF hop.

| state | config | observed | symptom | fix |
|---|---|---|---|---|
| **Working** | `TRUST_PROXY=2` (= in-cluster hops) | `.10` / protected | correct client IP recovered from the PROXY header | — |
| Misconfigured | `TRUST_PROXY=1` (too low) | **`.81`** / protected | admin notice shows the ingress address | `TRUST_PROXY=2` |
| Misconfigured | `TRUST_PROXY=3` (too high) | `.10` / **not protected** | bypassable | `TRUST_PROXY=2` |
| Misconfigured | unset | `.10` / **not protected** | bypassable | `TRUST_PROXY=2` |
| Misconfigured | `TRUST_PROXY=false` | **`.82`** / protected | collapses to the inner hop | `TRUST_PROXY=2` |
| **Misconfigured (infra)** | ingress does **not** consume PROXY protocol | **HTTP 400, no auth, no admin notice** | the whole site returns 400; ingress logs the literal `PROXY TCP4 …` line as the request | enable `use-proxy-protocol: "true"` (`listen … proxy_protocol; set_real_ip_from …; real_ip_header proxy_protocol`) at ingress |

**Answer to "does the value depend on how many hops sit inside the cluster?"**
Yes — exactly. `TRUST_PROXY` must equal the number of X-Forwarded-For-appending
**HTTP** proxies between Nightscout and the edge. The L4 PROXY-protocol load
balancer does not count. `n-1` reports the innermost proxy's address; `n+1` is
bypassable.

## unset == dev (no breaking change by default)

F1, `TRUST_PROXY` unset, measured on **both** trees:

| tree | O1 | O2 |
|---|---|---|
| dev `f1591069` | `172.31.66.10` | not protected |
| PR `81623f9b` | `172.31.66.10` | not protected |

Identical. Control: on dev, setting `TRUST_PROXY=1` changes nothing (dev does not
read the variable — the spoof still wins); on the PR the same value makes O2
protected. So the PR's default reproduces dev exactly, and the knob is PR-only.

## Failed-auth throttle (O3 / O4), `AUTH_FAIL_DELAY≈400 ms`

Behind F1 with `TRUST_PROXY=1` (resolved address = real client, immune to header
variation):

- **O3** guesser varying **both** credential and forwarding header: attempt 1 ≈ 2 ms,
  attempts 2-5 ≈ 320-350 ms → **throttled**. Under **unset** the same loop stays
  ≈ 1.5-3 ms → **not throttled** (a fresh key every attempt). *(This is the
  non-vacuity control for O3: throttled in one cell, not throttled in another.)*
- **O4a** bystander `.12` with the correct secret while `.10` is throttled: ≈ 4 ms → **not delayed**.
- **O4b** legitimate request at the **same** IP `.10` with the correct secret:
  - PR tree `81623f9b` (wait held on the failed path): ≈ 3 ms → **not delayed**.
  - delay-order tree `f6f361b1` (wait before the credential check, as on dev):
    ≈ 278 ms → **delayed**. This documents the cost of dev's ordering: a valid
    request sharing a real IP with a guesser (shared home / CGNAT / carrier NAT)
    waits too.

## O5 — TLS termination

Behind the TLS front end (self-signed, `X-Forwarded-Proto: https`) with
`INSECURE_USE_HTTP=false`: `GET /` → **200, 0 redirects, no loop** (unset and
`TRUST_PROXY=1`). Control: the same server over plain HTTP (`X-Forwarded-Proto:
http`) returns **307 → https**, so the redirect is active and the 200 is real.

## O2 across all header families

`o2_families.sh`, tree `f6f361b1` (`bf2/auth-delay-dev-order`; `lib/server/client-ip.js`
identical to the PR's). For each topology, for `TRUST_PROXY` unset and for that
topology's right setting, and for each probe in the private probes file, it boots
Nightscout on its own database and sends the probe through the real front end as a
failed authentication, then sends it again with a second value. A probe is a
caller-supplied value in one of the client-address header families the compatibility
mode reads. A cell is **protected** only if no probe, on any attempt, moved the address
in the admin notice. Liveness is asserted after every probe, so a dead server records
an error, not a pass. Which headers and values were sent, and the per-probe results, are
private.

| topology | `TRUST_PROXY` unset | right setting |
|---|---|---|
| F0 direct | not protected | `false`: protected |
| F1 nginx append | not protected | `1`: protected |
| F2 nginx replace | not protected | `1`: protected |
| F3 two appending hops | not protected | `2`: protected |
| F4 Caddy | not protected | `1`: protected |
| F5 Traefik | not protected | `1`: protected |
| F6 HAProxy `option forwardfor` | not protected | `1`: protected |
| TLS nginx | not protected | `1`: protected |
| L-B PROXY-protocol chain | not protected | `2`: protected |

Sanitised summary: `results/o2-families-2026-09-24.md`. Unset is not protected on all
nine topologies, including the three whose proxy replaces or rebuilds
X-Forwarded-For (F2, F4, F5). The right setting is protected on all nine.

## F7 — a front end that sends `address:port` (Azure App Service form)

`frontends/f7-azure-port-emulation.conf`: nginx at `172.31.66.90` appending the
client as `$remote_addr:$remote_port`, the form Azure App Service is reported to
send. It is not part of `lab.sh up`; start it by hand with `nginx_c` (see the
file). Measured 2026-09-24, O1 for the honest client `.10`:

| `TRUST_PROXY` | PR `81623f9b` | `9c6cde72` (explicit modes remove a numeric port) |
|---|---|---|
| `1` | `.90` (front end) | `.10` |
| `172.31.66.90` | `.90` (front end) | `.10` |
| unset | `.10` | `.10` |
| `false` | `.90` | `.90` (control: direct-only, as intended) |

This emulates the header shape only; it is not a measurement of Azure.

## Non-vacuity controls (each observable shown able to fail)

- O1 takes the correct value (`.10`) in some cells and a wrong value (peer `.20`
  / `.31` / `.82`, or inner proxy `.30` / `.81`) in others.
- O2 is protected in some cells and not protected in others on the identical setup,
  in both the X-Forwarded-For run and the all-families run (unset vs the right setting,
  same front end, same probes).
- O3 throttles in one cell and does not in another.
- O5 returns 200 over TLS and 307 on the negated control.
- `TRUST_PROXY=1` protects on the PR and does nothing on dev.

## What this lab does NOT prove

- **Hosted-PaaS edges** (Heroku, Azure App Service, DigitalOcean App Platform, and
  the real DigitalOcean LB / DOKS ingress) cannot be reproduced locally. Their
  actual header/PROXY-protocol behaviour must be cited from vendor docs, not
  inferred from this emulation.
- The **exact per-provider hop count** in production — the lab shows the *rule*
  (`TRUST_PROXY` = number of in-cluster XFF-appending HTTP hops), not any one
  deployment's number.
- **Header families beyond X-Forwarded-For** are exercised by `o2_families.sh`, but
  only with the probes in the private file; the tracked record says protected or not
  protected per cell and nothing about which probe moved the address. A family or
  value outside the private set is not covered.
- **Settings other than unset and the right one** (a hop count one off, `true`, a
  list) were exercised with X-Forwarded-For only. Explicit settings read only
  X-Forwarded-For, so this is their whole header surface.
- Real client TLS/SNI, HTTP/2, WebSocket upgrades through every proxy, or
  provider-specific health-check traffic.

## Running it

```
PROXYLAB_STATE=/some/dir/outside/any/git/tree \
DEV_TREE=…/externals/work/crm-s66-lab-dev \
PR_TREE=…/externals/work/crm-bf2-auth \
DELAY_TREE=…/externals/work/crm-bf2-delay-order \
./lab.sh up            # network + mongo + front ends + clients
./lab.sh status        # assert everything is up
./lab.sh run           # honest matrix -> results/ JSON + markdown
# adversarial cells (O2/O3) only when the private probes are provided:
PROXYLAB_PRIVATE_PROBES=…/tmp/proxy-trust-lab/probes.json ./lab.sh run
./lab.sh down          # STOP (do not remove) every s66lab-* container + host servers
```

O2 across all header families (needs the stack from `./lab.sh up`):

```
PROXYLAB_STATE=… DELAY_TREE=…/externals/work/crm-bf2-delay-order \
PROXYLAB_PRIVATE_PROBES=…/tmp/proxy-trust-lab/probes.json \
PROXYLAB_PRIVATE_RESULTS=…/tmp/proxy-trust-lab/results \
O2_TOPOS="F1 F4" \
./o2_families.sh      # O2_TOPOS optional; omit for all nine
```

Both private variables are required; the script refuses to start without them.
`PROXYLAB_PRIVATE_RESULTS` must be a gitignored directory: the per-probe JSON lines go
there. `O2_TOPOS` is optional (default all nine: `F0 F1 F2 F3 F4 F5 F6 TLS LB`).
`O2_TREE` overrides the tree (default `DELAY_TREE`, then `PR_TREE`). The sanitised
summary is written to `$PROXYLAB_STATE/out/o2-families-<date>.md`; copy it into
`results/` by hand after checking it names no header.

Honest-client cells always run. The O2/O3 adversarial cells run only when
`$PROXYLAB_PRIVATE_PROBES` is set; without it the tracked runner exercises only
the honest path. `results/` carries the sanitised matrix (protected / not
protected, honest addresses only) — no header recipe.

## Disclosure

This repo is public and the compatibility-default weakness is live on the
shipping release. Describe the **mechanism** here, never the **recipe**. The
concrete spoofing header names/values and the guesser requests live only in the
gitignored private directory `externals/work/crm-bf2-delay-order/tmp/proxy-trust-lab/`.
