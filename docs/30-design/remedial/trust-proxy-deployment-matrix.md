# `TRUST_PROXY` deployment matrix

*Contributor-facing. Living document; facts dated 2026-09-24. Code anchor: `bf2/auth-delay-dev-order` at
`f6f361b1` (`lib/server/client-ip.js`, `lib/authorization/delaylist.js`, `lib/authorization/index.js`
`resolve()`), the fix branch for PR nightscout/cgm-remote-monitor#8754.*

**Status.** `TRUST_PROXY`: **open** (PR #8754, not merged to dev, not released). Every Nightscout release up to
and including 15.0.8 behaves as the "unset" column below and has no setting to change it. Nothing here is
fixed for operators until it is released.

This page maps each deployment shape to the `TRUST_PROXY` value it needs, what a correct and an incorrect
setting look like, and how to fix the incorrect one. Platform claims are research, not measurement; each
carries its source and a confidence level. Self-hosted rows marked **(lab)** were measured on 2026-09-24 in
[`tools/lab/proxy-trust/`](../../../tools/lab/proxy-trust/README.md) (direct, nginx appending and replacing,
two nginx hops, Caddy 2.8, Traefik v3.1, HAProxy 3.0 `option forwardfor`, nginx terminating TLS, and a
PROXY-protocol chain) against `lib/server/client-ip.js` at `81623f9b`, identical at `f6f361b1` and
`607d51b0`. Cells the lab did not run are still marked **(lab: pending)**.

**What protects the address is the setting, not the proxy.** When a trusted proxy or load balancer adds its
entry to a value the caller may have supplied, setting `TRUST_PROXY` to that trusted hop is what makes the
difference: Nightscout reads the entry that hop added and nothing to its left. Measured (lab, all
client-address header families the unset mode reads): with `TRUST_PROXY` unset, **not protected** on all nine
lab topologies, including nginx `$remote_addr`, Caddy and Traefik, which replace or rebuild `X-Forwarded-For`;
with the right setting (`false` direct, `1` one proxy, `2` two hops or the PROXY-protocol chain),
**protected** on all nine. A replacing proxy does not make the unset default protected.

Operator-facing versions: the Nightscout docs page *Proxy setting (`TRUST_PROXY`)* (draft,
`nightscout.github.io` `docs/nightscout/trust_proxy.md`) and the cgm-remote-monitor reference
`docs/proposals/trusted-proxy-migration.md`.

## 1. What Nightscout does with each value (reproduced at `f6f361b1`)

These rows were reproduced on 2026-09-24 by calling `createClientIP()` and an Express app with
`compileTrust()` directly in the worktree (not read from code). "Peer" is the address of the TCP connection
Nightscout accepted; "chain" is the `X-Forwarded-For` list, left to right.

| `TRUST_PROXY` | Client address used for the failed-login delay and the "Failed authentication" notification | `X-Forwarded-Proto` believed (https redirect) | Startup log |
|---|---|---|---|
| unset / empty | Read from forwarding headers any caller can set (the `forwarded-for` package, as on every release) | yes, from any peer | `console.warn`: `SECURITY: failed-authentication throttling is keyed on the client address, and TRUST_PROXY is not set, …` |
| `false` | The peer. Behind a proxy this is the proxy's address, so **every client shares one address** | no — only a TLS socket counts as https | `console.info`: `Failed-authentication throttling is keyed on the client address as resolved through TRUST_PROXY=false.` |
| `n` (1, 2, …) | The chain entry added by the proxy `n` hops away. If the chain is shorter than `n`, the left-most entry, which the caller may have supplied | yes, when `n` ≥ 1 | `console.info`: `… as resolved through TRUST_PROXY=1: the X-Forwarded-For entry added by the proxy 1 hop from Nightscout.` |
| `true` | The left-most chain entry | yes | `console.warn`: `SECURITY: … TRUST_PROXY=true trusts every proxy hop, so that address is the left-most X-Forwarded-For entry. …` |
| IP / CIDR list | Walks right to left past listed addresses; the first unlisted address. If the peer is not listed, the peer | only when the peer is listed | `console.info`: `… as resolved through TRUST_PROXY=<value>.` |
| anything else (`0`, negative, fraction, number mixed with addresses, `loopback`/`linklocal`/`uniquelocal`) | Nightscout does not start: `TRUST_PROXY must be false, true, a whole number of proxy hops (1 or more), or a comma-separated list of proxy IP addresses or CIDRs` (plus a suffix naming the problem) | — | — |

Properties that decide the per-platform rows:

- **Explicit modes read only `X-Forwarded-For`.** Platform-specific client headers (`Fly-Client-IP`,
  `do-connecting-ip`, `CF-Connecting-IP`, `True-Client-IP`, `X-Client-IP`, `X-Real-IP`) are not read by any
  explicit mode. Where a platform puts the client only in such a header, no explicit value yields a per-client
  address.
- **A numeric port is removed.** An entry of the form `address:port`, `[v6]:port` or `[v6]` resolves to the
  address in every explicit mode (`9c6cde72`); other malformed entries fall back to the peer. The unset mode
  strips IPv4 ports, as before. This is what makes `1` usable on Azure App Service (§3).
- **Too many hops fails towards the caller's claim, and looks correct in a simple test.** With `n` larger than
  the real hop count, a client that sends no header still resolves to its own address, so a phone test passes;
  a client that sends a chain gets its own left-hand entry believed. Operators must use the **smallest** `n`
  that shows a real client address.
- **Too few hops fails towards a shared address.** The address resolved is a proxy's, so all clients share one
  delay and the notification shows a provider or private address.
- **A hop count trusts whatever connects.** If the origin is reachable without the proxy (for example a home
  server's port also open to the internet, or a CDN origin not firewalled to the CDN), a direct caller is
  counted as hop 1. Only a list, or a firewall, closes that.
- **An address list that misses the real proxy disables https detection.** Reproduced: a list not containing
  the peer made `req.secure` false with a forwarded https header present, which is the redirect loop when
  `INSECURE_USE_HTTP=false`.

## 2. The failed-login delay (what the address is used for)

`AUTH_FAIL_DELAY` (milliseconds, default `5000`). Each failed password or token check adds that delay to two
keys: the client address and the credential tried (`delaylist.js` `keysFor`, `addFailedRequest`; successive
failures extend the entry from its current expiry). **The wait happens before the credential is checked**
(`index.js` `resolve()`, lines 151-164 at `f6f361b1`, the order of every earlier release): any request whose
address or credential has a pending entry sleeps for the longest pending delay first, including a request with
the correct credential and a request with no credential. A success clears both keys.

Consequences for deployment:

- With the address resolved correctly, only clients that truly share a public address share a delay: one home
  network behind one router, or a mobile carrier's shared (CGNAT) address. Example: a caregiver's phone on the
  same Wi-Fi as an uploader configured with an old `API_SECRET` waits on every request while that uploader
  keeps failing. The credential key follows the old secret wherever the uploader connects from.
- With the address resolved to a proxy (`false` behind a proxy, too few hops), every
  client shares that delay: one misconfigured uploader slows every viewer and every uploader.
- With `TRUST_PROXY` unset, the address comes from headers any visitor can set, so the delay does not protect
  against guessing (the startup `SECURITY:` line says so). The default stays unset in 15.0.9 by maintainer
  decision (compatibility default plus opt-in setting; flip in a later planned release).

## 3. Platform research

Confidence: **high** = the vendor's own documentation states it; **medium** = a vendor staff statement, or
consistent measured third-party reports; **low** = one report, contradictory statements, or inference.
Where sources conflict the table says so and does not choose.

| Platform | Edge `X-Forwarded-For` handling | Proxy hops in front of the app | TLS / `X-Forwarded-Proto` | Proxy source addresses | Own client-IP header | Recommended `TRUST_PROXY` | Confidence | Sources |
|---|---|---|---|---|---|---|---|---|
| **Heroku** (Common Runtime) | Appends the address that connected to the router | 1 (router; the TLS load balancer in front is not recorded in the chain per the docs) | Terminated at the load balancer; sets `X-Forwarded-Proto`, `X-Forwarded-Port` | Not stable (only Private Spaces documents stable router IPs) | none | `1` | high for append / proto; medium for hop count (docs do not state it) | [Heroku HTTP routing](https://devcenter.heroku.com/articles/http-routing) |
| **Railway** | **Conflicting.** Staff 2026-03-09: "our edge proxy appends to the chain", leftmost is the client. Staff (earlier thread): "We do strip X-Forwarded-For at our edge". Staff (2024 thread): the rightmost value is trustworthy. Traffic may or may not pass a Fastly CDN layer | 1 without the CDN path is the community consensus; not documented; may differ on the CDN path | Terminated at the edge (`tcp-proxy`); proto not documented | Community reply: 100.0.0.0/8; one report shows 100.64.0.0/10 addresses. Not documented by Railway | `X-Real-IP` (staff: currently set to the CDN edge on the CDN path, a known bug); `Fastly-Client-IP` on the CDN path | `1`, then **verify** with the notification test (§5) | low | [edge networking](https://docs.railway.com/networking/edge-networking); [staff 2026-03-09](https://station.railway.com/questions/which-header-should-i-rely-on-for-real-c-d78a6f96); [conflicting thread](https://station.railway.com/questions/security-critical-questions-on-edge-prox-8fddd775); [2024 thread](https://station.railway.com/questions/edge-proxy-x-forwarded-for-and-x-real-ip-c5a50049); [chain shape](https://station.railway.com/questions/x-forwarded-for-and-x-real-ip-127-0-0-1-dc17c205) |
| **Render** | **Conflicting.** Staff 2021-05-28: "we set the first IP in the list to the real client IP"; a user in the same thread: Render "only appends". A measured 2026-09 third-party report: chain of three entries, visitor then a Cloudflare edge then a Render-internal address; one trusted hop resolved every visitor to the internal address | 3 by the measured report (Cloudflare edge, Render internal, peer) | Terminated by Render's load balancer; proto not documented on the page read | Not published; the Cloudflare hop's ranges are published | none documented | `3`, **verify**; an address list of private ranges plus Cloudflare's published ranges is the non-count alternative | low | [Render web services](https://render.com/docs/web-services); [feedback thread](https://feedback.render.com/features/p/send-the-correct-x-forwarded-for); [measured report](https://github.com/Het415/listinglens/pull/10) |
| **Fly.io** | Docs warn the header "must be treated with caution to avoid spoofing"; community (2022, non-staff): the last chain entry is a Fly address, and `2` "seemed effective" | 2 by community report (Fly edge recorded in the chain, plus the local proxy as peer) | Proxy sets `X-Forwarded-Proto`, `X-Forwarded-SSL` | Not published | `Fly-Client-IP` (not read by Nightscout) | `2`, **verify** | low | [request headers](https://docs.fly.io/networking/request-headers/); [community thread](https://community.fly.io/t/recommended-setting-for-trust-proxy-on-express/6346) |
| **Azure App Service** | Append vs replace **not documented**. Reported and measured (2017, 2026-09-22): the client is sent as `address:port` | 1 per Microsoft's own Express example (`trust proxy` 1) | Terminated at the front ends; app must read `X-Forwarded-Proto` | Not stable | `X-Client-IP` reported, not read by Nightscout | `1`, **verify** (port-bearing entries are accepted since `9c6cde72`; lab F7 emulates the `address:port` form) | medium (port suffix: two independent reports, one measured 2026-09-22; not in Microsoft docs) | [Node on App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-language-nodejs); [request-ip #29](https://github.com/pbojinov/request-ip/issues/29); [measured PR](https://github.com/pepti/hallismiley/pull/166) |
| **Google Cloud Run** (run.app, no load balancer) | Appends the client as the right-most entry (third-party PRs; not in the container contract) | 1 | Terminated by Cloud Run; proto header not documented on the contract page | Not applicable (serverless) | none | `1` | medium | [container contract](https://docs.cloud.google.com/run/docs/container-contract); third-party: [PR](https://github.com/UofUEpiBio/doim-explorer/pull/2) |
| **Cloud Run behind a global external Application Load Balancer** | The load balancer appends two entries, the client then the load balancer's own address, after any caller-supplied value | 2 | LB sets `X-Forwarded-Proto` | GFE ranges do not apply to serverless backends | none | `2` | medium (LB behaviour is documented; the Cloud Run hop after it is inferred) | [ALB overview](https://docs.cloud.google.com/load-balancing/docs/https); [regional LB report](https://discuss.google.dev/t/http-x-forwarded-for-only-pass-the-real-client-ip-if-the-load-balancer-is-global-cloud-run/98724) |
| **DigitalOcean App Platform** | **Conflicting.** DO support doc: the header carries "the IP address of the DigitalOcean ingress server". A 2021 user test: the header contains the client | unknown | Terminated by DO ingress | Not published | `do-connecting-ip` (not read by Nightscout) | **No reliable value known.** Leave unset; if testing, `1` and verify | low | [DO support](https://docs.digitalocean.com/support/where-can-i-find-the-client-ip-address-of-a-request-connecting-to-my-app/); [community 2021](https://www.digitalocean.com/community/questions/client-ip-on-app-platform) |
| **DigitalOcean Load Balancer / DOKS** | See §4 | — | — | "Backend IP addresses may change at any time" | — | see §4 | — | §4 |
| **Northflank** | "attached to all HTTP/S requests by the Northflank load balancer"; append vs replace not documented | not documented | not documented on the page read | not documented | none documented | `1`, **verify** | low | [networking](https://northflank.com/docs/v1/application/network/networking-on-northflank) |
| **Koyeb** | Appends the connecting address; "the last IP of the x-forwarded-for is the only IP we can certify as valid" | 1 as recorded in the chain (edge; the service mesh is not documented as adding an entry) | Terminated at the edge; proto header not mentioned | not published | none | `1` | medium | [edge network](https://www.koyeb.com/docs/reference/edge-network) |
| **Cloudflare proxy** (orange cloud) | Appends the connecting address to any existing chain | +1 in front of whatever is next | Sets `X-Forwarded-Proto` | **Published**: <https://www.cloudflare.com/ips/> | `CF-Connecting-IP`; `True-Client-IP` on Enterprise (not read by Nightscout) | Adds one to the count behind it: Cloudflare → Nightscout `1` only if the origin accepts Cloudflare only; Cloudflare → nginx → Nightscout `2`; or a list (see §5 row D) | high | [Cloudflare headers](https://developers.cloudflare.com/fundamentals/reference/http-headers/) |
| **Cloudflare Tunnel** (`cloudflared`) | Visitor address appended at the right of any caller-supplied chain (open bug report asks for the opposite order) | 1 (`cloudflared` is the peer); +1 per local proxy after it | **Conflicting**: Cloudflare docs say the edge sets `X-Forwarded-Proto`; a closed 2024 issue reports the origin sees http when `cloudflared` forwards to an http service | local | `CF-Connecting-IP` | `1` (tunnel straight to Nightscout); `2` with a local proxy between | medium (hop), low (proto) | [cloudflared #1426](https://github.com/cloudflare/cloudflared/issues/1426); [cloudflared #1245](https://github.com/cloudflare/cloudflared/issues/1245) |
| **VPS / home server + nginx** | `$proxy_add_x_forwarded_for` appends; `$remote_addr` replaces; **no directive passes the caller's header through unchanged and adds nothing** | 1 | Wherever TLS ends; nginx sets `X-Forwarded-Proto` only if configured | local: `127.0.0.1` or the host's bridge address | none | `1`, **after** making nginx add the header (the Nightscout docs' Ubuntu example sets none, see §6). Lab: append and replace with `1` resolve the client, protected; unset not protected with either; no-directive config not run (B6) | high (nginx semantics; lab) | nginx `proxy_set_header`; [Ubuntu guide](https://nightscout.github.io/nightscout/ubuntu/) |
| **VPS + Caddy** | Ignores the caller's `X-Forwarded-For` by default and sets its own ("to prevent spoofing") | 1 | Sets `X-Forwarded-Proto` | local | none | `1` (`true` also resolves correctly, but logs a warning). Lab: `1` resolves the client, protected; unset not protected | high (lab for `1` and unset) | [Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) |
| **VPS + Traefik**, and the shipped **docker-compose** | From an untrusted peer, discards the caller's `X-Forwarded-For` and appends the peer, so the chain is the client alone | 1 | Rebuilds `X-Forwarded-Proto` from the connection | container address on the compose network, not stable | none | `1`. Lab (Traefik v3.1, file provider, fixed container addresses): `1` resolves the client, protected; unset not protected. The shipped compose file and Docker port publishing not run (C1, C3) | high (source code; lab) | [forwarded_header.go](https://raw.githubusercontent.com/traefik/traefik/master/pkg/middlewares/forwardedheaders/forwarded_header.go); [entrypoints](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/); [traefik #12001](https://github.com/traefik/traefik/issues/12001) |
| **VPS + Apache** (`mod_proxy_http`) | Appends ("will contain more than one (comma-separated) value if the original request already contained one") | 1 | **Does not set `X-Forwarded-Proto`** by default; operator must add it or Nightscout redirects forever with `INSECURE_USE_HTTP=false` | local | none | `1` (lab: pending) | high | [mod_proxy](https://httpd.apache.org/docs/2.4/mod/mod_proxy.html) |
| **VPS + HAProxy** | `option forwardfor` appends (lab, HAProxy 3.0: a caller's chain is kept and the peer added); `if-none` keeps a caller's header instead | 1 | only if configured | local | none | `1`, never with `if-none`. Lab: `option forwardfor` with `1` resolves the client, protected; unset not protected; `if-none` not run (lab: pending) | high for `option forwardfor` (lab); medium for `if-none` (the tutorial page does not state append vs replace) | [HAProxy XFF tutorial](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/proxying-essentials/client-ip-preservation/add-x-forward-for-header/) |
| **Kubernetes ingress-nginx** | Default `use-forwarded-headers: false`: replaces a caller's `X-Forwarded-For` with the request information it sees; `compute-full-forwarded-for: true` appends instead | 1 (ingress pod is the peer) | Sets `X-Forwarded-Proto` | pod addresses, not stable; do not infer a CIDR from a pod list | none | `1`. Meaningful only if the ingress sees real clients (PROXY protocol, or a source-preserving load balancer). **Project retired March 2026** (no further security fixes) | high | [ingress-nginx ConfigMap](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/); [retirement](https://www.kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/) |
| **T1Pal, NS10BE, other managed Nightscout** | the provider's | the provider's | the provider's | — | — | **Ask the provider.** The site owner does not control the proxy | — | — |

## 4. DigitalOcean Load Balancer and DOKS

Sources: [DOKS load balancer settings](https://docs.digitalocean.com/products/kubernetes/how-to/configure-load-balancers/),
[LB features](https://docs.digitalocean.com/products/networking/load-balancers/details/features/),
[CCM annotations](https://raw.githubusercontent.com/digitalocean/digitalocean-cloud-controller-manager/master/docs/controllers/services/annotations.md),
[PROXY with ingress-nginx](https://docs.digitalocean.com/support/how-do-i-enable-proxy-protocol-when-my-load-balancer-sends-requests-to-the-nginx-ingress-controller/),
[unhealthy after enabling PROXY](https://docs.digitalocean.com/support/why-did-all-of-my-backend-droplets-become-unhealthy-when-i-enabled-proxy-protocol-on-my-load-balancer/).

Established:

- DO load balancers "terminate client connection requests with proxy", so `externalTrafficPolicy: Local` does
  not preserve the client source address on the (regional HTTP) load balancer. (high)
- The default DOKS Service protocol (`do-loadbalancer-protocol`) is `tcp`. (high)
- The load balancer adds `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Port` only "when the entry and
  target protocols are HTTP, or HTTPS with a certificate (not passthrough)". In TCP mode, and with TLS
  passthrough, it adds no headers. So **in TCP mode with PROXY protocol, the client address travels only in the
  PROXY protocol header**; no `X-Forwarded-For` is sent by the load balancer. (high for "no headers in TCP /
  passthrough", stated by DO; "only in the PROXY header" follows, since a TCP-mode proxy cannot inject HTTP
  headers)
- PROXY protocol v1 only, on regional HTTP load balancers (not network load balancers). Network load
  balancers preserve the client source address instead. (high)
- In HTTP/HTTPS mode, whether the load balancer appends to or replaces a caller-supplied `X-Forwarded-For` is
  **not documented**. (unknown; lab can only model it)
- Backend (source) addresses "may change at any time and should not be used to configure firewalls", so an
  address list for the load balancer is not feasible. (high)
- With PROXY protocol, in-cluster requests to the load balancer's address can bypass it (kube-proxy); DO's
  `do-loadbalancer-hostname` annotation is the documented workaround. (high)

| Mode | What reaches Nightscout | `TRUST_PROXY` | Lab |
|---|---|---|---|
| TCP + PROXY protocol, ingress-nginx `use-proxy-protocol: "true"` (default `use-forwarded-headers: false`) | ingress-nginx takes the client from the PROXY header and sends a chain containing only that client; peer = ingress pod | `1` | Rule measured (lab): an nginx stream front with `proxy_protocol on` is not an `X-Forwarded-For` hop; the value counts only the appending HTTP proxies after it. Ingress straight to Nightscout was not run separately (the lab chain has one further hop, next row) |
| Same, with further proxies between ingress and Nightscout, each appending | chain grows by one per appending hop | `1` + number of appending hops after the ingress | Lab (stream front → nginx consuming PROXY protocol, appending → one appending nginx → Nightscout): `2` resolves the client, protected; `1` resolves the ingress address; `3` resolves the client but is not protected; `false` resolves the inner hop; unset not protected |
| TCP, no PROXY protocol on either side | site works; ingress sees the load balancer / node address for everyone | any value resolves a shared address; fix the chain first (enable PROXY on both sides) | (lab: pending) |
| HTTP/HTTPS mode (LB terminates TLS) → ingress-nginx default | ingress replaces the LB's chain with the LB's address | shared address for everyone. Prefer TCP + PROXY. The alternative (`use-forwarded-headers: true` with `proxy-real-ip-cidr`) needs the LB's source range, which DO says changes | (lab: pending); LB append/replace unknown |
| HTTP/HTTPS mode → Droplet with Nightscout directly | LB-added chain; peer = LB | `1` if the LB appends or replaces with the client (undocumented) | (lab: pending) |
| TLS passthrough | no headers; TLS ends at the backend | TCP + PROXY rules apply | — |

**Misconfigured PROXY protocol (site-down, not a `TRUST_PROXY` problem):**

| State | Observed | Symptom the operator sees | Fix |
|---|---|---|---|
| LB sends PROXY, ingress not consuming it | the backend reads the PROXY line as the start of an HTTP request and answers 400; DO: "those Droplets give a 400 response to the load balancer's health checks", the LB marks them unhealthy and stops routing | site unreachable (LB error page); all backends unhealthy in the DO control panel | set `use-proxy-protocol: "true"` in the ingress-nginx ConfigMap, or remove the annotation. Lab (nginx stand-in): the ingress answers **HTTP 400**, logs the PROXY line as the request, and Nightscout sees no request (no authentication, no notification) |
| ingress expects PROXY, LB not sending it | nginx rejects the connection; error log reports a broken PROXY header | site unreachable; TLS or connection errors in browsers and uploaders | add `service.beta.kubernetes.io/do-loadbalancer-enable-proxy-protocol: "true"` (a string, per DO) to the ingress Service, or disable `use-proxy-protocol` (lab: pending for the exact log line) |
| Both enabled, Nightscout `TRUST_PROXY=false` | peer = the hop nearest Nightscout for everyone (lab: the inner hop's address) | everyone slowed together after one failure; notification shows a pod address; redirect loop if Nightscout enforces https | `TRUST_PROXY=1` |

## 5. Scenario matrix (working / misconfigured / fix)

Row shape matches the lab's output: topology | state | config | observed | symptom | fix. **(lab)** marks an
observed value measured on 2026-09-24 (see the introduction); "protected" means no caller-supplied value moved
the address. **(lab: pending)** marks a value the lab did not run; the expected value is given from §1.

| # | Topology | State | Config | Observed (expected → lab) | Symptom | Fix |
|---|---|---|---|---|---|---|
| A1 | Direct (no proxy; Nightscout TLS or LAN http) | working | `false` | peer = real client; protected (lab) | log: `… resolved through TRUST_PROXY=false.` | — |
| A2 | Direct | misconfigured | unset | the honest client's own address, but not protected: a caller-supplied value moves it (lab) | `SECURITY:` line at startup | `false` |
| A3 | Direct | misconfigured | `1` or `true` or a list containing client ranges | a direct caller is treated as a proxy; its chain is believed: not protected (lab, `1`; `true` and a list not run) | **none visible** for `1` / list (info line logged); `true` logs `SECURITY:` | `false` |
| B1 | One local proxy that appends (nginx `$proxy_add_x_forwarded_for`, Apache, HAProxy `forwardfor`) | working | `1` | the entry the proxy added = client; protected (lab: nginx append, HAProxy `option forwardfor`, nginx terminating TLS; Apache not run) | hop info line; notification shows the phone's public address | — |
| B2 | One local proxy that replaces (Caddy, Traefik, nginx `$remote_addr`) | working | `1` | client; protected (lab: nginx `$remote_addr`, Caddy, Traefik) | as B1 | — |
| B3 | One local proxy | misconfigured | `false` | proxy address for everyone (lab: nginx, the proxy's address; two hops, the inner proxy's). Redirect loop from §1, not run in the lab | redirect loop if the proxy terminates TLS and `INSECURE_USE_HTTP=false`; otherwise everyone slowed together; notification shows `127.0.0.1` / a container address | `1` |
| B4 | One local proxy | misconfigured | `2` or more | honest client resolves correctly, but a caller's own left-hand entry is believed: not protected (lab: `2` behind one nginx, `3` behind two hops and behind the PROXY-protocol chain) | none in a phone test (phone sends no chain, so it resolves correctly) | `1` |
| B5 | Appending proxy | misconfigured | `true` | left-most = caller's claim: not protected (lab, nginx append) | `SECURITY: … TRUST_PROXY=true …` at startup | `1` |
| B6 | nginx with **no** `X-Forwarded-For` directive (the Nightscout Ubuntu guide's config) | misconfigured | `1` or a loopback list | clients that send nothing share the peer address; a caller-supplied chain passes through and is believed (lab: pending) | everyone slowed together; notification shows `127.0.0.1` | add `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` (or `$remote_addr`), then `1` |
| B7 | Local proxy, list mode | misconfigured | list missing the proxy's real address (e.g. `127.0.0.1` while the proxy connects over `::1`, or a changed container address) | peer untrusted: https not detected, address = peer (reproduced for https; lab: a list without the proxy's address resolves the proxy's address, protected; lab: pending for `::1` and IPv4-mapped peers) | redirect loop | correct the list, or use `1` |
| B8 | Apache, TLS at Apache | misconfigured | any, `INSECURE_USE_HTTP=false` | no `X-Forwarded-Proto` sent (lab: pending) | redirect loop in every mode | add `RequestHeader set X-Forwarded-Proto "https"` in the TLS virtual host |
| C1 | Shipped docker-compose (Traefik, `INSECURE_USE_HTTP: 'true'`) | working | `1` | client, if Traefik sees the client's address (lab: Traefik v3.1 with `1` resolves the client, protected; the shipped compose file and its port publishing not run) | hop info line | — |
| C2 | docker-compose | misconfigured | `false` | Traefik's container address for everyone; no redirect loop because the compose file sets `INSECURE_USE_HTTP: 'true'` (lab: `false` resolves the proxy's address behind nginx; not run behind Traefik or on the compose file) | everyone slowed together; notification shows a `172.x` address | `1` |
| C3 | docker-compose where Docker's port publishing hides the client (userland proxy, rootless Docker, some IPv6 setups) | misconfigured upstream | `1` | Docker's gateway address for everyone (lab: pending) | everyone slowed together; notification shows the Docker gateway | fix port publishing (host networking for Traefik, or a source-preserving setup); not fixable with `TRUST_PROXY` |
| D1 | Cloudflare proxy → local nginx (appending) → Nightscout | working | `2` | the entry Cloudflare added (lab: pending, lab models Cloudflare as an appending front) | notification shows the phone's address | — |
| D2 | same | misconfigured | `1` | a Cloudflare edge address, shared by many visitors (lab: pending) | notification shows an address in Cloudflare's published ranges; unrelated visitors share delays | `2` |
| D3 | same, origin also reachable without Cloudflare | misconfigured | `2` | a direct caller supplies both entries (lab: pending) | none visible | firewall the origin to Cloudflare's ranges, or use a list: the local proxy address plus Cloudflare's published ranges (kept current by the operator) |
| D4 | Cloudflare → nginx that **replaces** with `$remote_addr` → Nightscout | misconfigured | `1` or `2` | a Cloudflare edge address (lab: pending) | as D2 | make nginx append, or restore the client with nginx's real-ip module limited to Cloudflare's ranges |
| E1 | Cloudflare Tunnel → Nightscout | working | `1` | visitor (lab: not reproducible locally) | notification shows the phone's address | — |
| E2 | Cloudflare Tunnel → nginx → Nightscout | working | `2` | visitor | as E1 | — |
| F1 | Hosted platform (§3) | working | the §3 value | client | notification test passes at the smallest value | — |
| F2 | Hosted platform | misconfigured | too small | provider or CDN address for everyone | everyone slowed together; notification shows a private (`10.`, `172.16–31.`, `192.168.`, `100.64–127.`) or provider address | raise by one, re-test, stop at the first value showing the phone's address |
| F3 | Hosted platform | misconfigured | `false` | provider address for everyone | redirect loop (all listed platforms terminate TLS) | unset, or the §3 value |
| F4 | Azure App Service | working | `1` | client; the port on Azure's entry is removed (lab F7: `address:port` front end resolved the client with `1` and with a list, 2026-09-24, `9c6cde72`; not measured on Azure itself) | notification test passes | — |
| G | DOKS / DO LB | see §4 | | | | |
| H | Managed Nightscout (T1Pal, NS10BE) | — | provider-controlled | — | — | ask the provider |
| any | any | misconfigured | typo in the variable name, value not saved, app not restarted, `.env` not passed to the container | unset behaviour | `SECURITY:` line still logged | set it where Nightscout reads it (Azure's `CUSTOMCONNSTR_TRUST_PROXY` also works), restart |
| any | any | misconfigured | invalid value | Nightscout exits at startup | log: `TRUST_PROXY must be false, true, a whole number of proxy hops (1 or more), or a comma-separated list …` | correct or remove the value |

**Undo for every row:** remove `TRUST_PROXY` (or set it empty) and restart. That restores the behaviour of
every earlier release, including https detection behind any proxy.

**Verification procedure (hosted and self-hosted).** From a phone on mobile data (Wi-Fi off), sign in with a
deliberately wrong API secret once, then sign in correctly on another device and open the admin
notifications. The "Failed authentication" message reads `A device at IP address %1 attempted
authenticating with Nightscout with wrong credentials. …`; `%1` is the resolved address. It should equal the
phone's public address as a "what is my IP" page on that phone shows it. Because a too-large hop count also
passes this test, start at `1` and increase only while the address shown is a provider's or a private one.
The test itself puts one `AUTH_FAIL_DELAY` on the phone's address and on the wrong secret.

## 6. Existing claims checked (flagged, not changed)

| Where | Claim | Finding | Evidence |
|---|---|---|---|
| `crm` `docs/proposals/trusted-proxy-migration.md`, Deployment guidance | "Docker, nginx/Apache, Heroku and Azure: existing edge-managed proxy setups can use the compatibility default without guessing provider address ranges." | **Misleading.** They keep working, but the compatibility default leaves the failed-login delay ineffective on all of them. Measured (lab): unset is not protected behind nginx (appending or replacing), Caddy, Traefik and HAProxy; a replacing proxy does not make the unset default protected. Setting `TRUST_PROXY` to the hop count (`1`) is protected behind each, and needs no address ranges on nginx, Apache, Traefik, Caddy and Heroku. Azure is the exception: explicit values currently collapse to a shared address because of the port suffix | §1, §3, lab |
| same, Kubernetes / ingress-nginx bullet | "existing sanitized HTTP forwarding behind TLS termination works with the default" | **Incomplete.** An edge that overwrites `X-Forwarded-For`, as ingress-nginx's default does, does not make the unset default protected (lab: replacing and rebuilding proxies measured not protected under unset; ingress-nginx itself not run). Set `TRUST_PROXY` to the hop count: `1` with ingress-nginx straight to Nightscout, which survives ingress pod replacement | ingress-nginx ConfigMap doc; §1; lab |
| same, Compatibility boundary | "The proxy must overwrite untrusted forwarded headers" | Not sufficient. Measured (lab): proxies that overwrite or rebuild `X-Forwarded-For` (nginx `$remote_addr`, Caddy, Traefik) leave the unset default not protected. The boundary is `TRUST_PROXY` set to the trusted hop count, not a proxy configuration | §3, lab |
| same, HTTPS paragraph | "Disabling Nightscout's HTTPS enforcement is not necessary to solve the ingress redirect loop." | True for unset, a hop count, `true`, and a list that contains the proxy; false for `false` and for a list missing the proxy | §1 reproduced |
| same, intro and Validation | "The production Kubernetes trial exposed redirect loops …", "That migration is superseded", "Rollback of this compatibility correction restores the mandatory explicit-IP candidate behavior" | Review narrative ("was X, now Y"), not current fact. The revised draft replaces the intro; the rollback sentence is flagged | — |
| same, header note | "This branch (bf2/auth-hardening) differs from chore/nightscout-modernization …" | The worktree branch is `bf2/auth-delay-dev-order`; the note describes the backport difference that `client-ip.js` documents and is otherwise accurate | `client-ip.js` comment |
| `nightscout.github.io` `docs/nightscout/ubuntu.md` nginx block | sets `Host`, `Upgrade`, `Connection`, `X-Forwarded-Proto`, no `X-Forwarded-For` | With this config any explicit `TRUST_PROXY` value believes a caller-supplied chain (nginx forwards it unchanged and adds nothing) and resolves everyone else to `127.0.0.1` | §5 B6 (lab: pending; nginx semantics) |
| `crm` `docker-compose.yml` | `INSECURE_USE_HTTP: 'true'` | Not wrong; it means `TRUST_PROXY=false` does not loop on the shipped compose file but still collapses every client to Traefik's address | file at `f6f361b1` |

**Code gap:**

1. **Platform client headers are not readable** in explicit modes (DO App Platform's `do-connecting-ip`,
   Fly's `Fly-Client-IP`, Cloudflare's `CF-Connecting-IP`). On DO App Platform, if the support doc is right, no
   value gives a per-client address.

## 7. Lab coverage

Measured 2026-09-24 ([lab README](../../../tools/lab/proxy-trust/README.md), results in
`tools/lab/proxy-trust/results/`):

- B1/B2/B4/B5: nginx append and replace, Caddy, Traefik, HAProxy `option forwardfor`, nginx terminating TLS,
  with `1` resolve the client, protected. Behind one nginx, `2` and `true` resolve the honest client but
  believe a caller's chain.
- A1-A3: direct, `false` protected; unset and `1` not protected.
- B3: `false` behind nginx resolves the proxy's address (the inner proxy's with two hops).
- Two appending hops: `2` protected; `1` the inner proxy's address; `3` not protected.
- DO-style chain (§4): nginx stream `proxy_protocol on` → nginx consuming PROXY protocol → one further nginx:
  `2` protected; `1` the ingress address; `3` not protected; ingress not consuming PROXY protocol → HTTP 400.
- Unset, across every client-address header family the unset mode reads: not protected on all nine
  topologies; the right setting protected on all nine.
- TLS termination: 200 with no redirect loop under unset and `1`; the plain-HTTP control redirects (307).

Not run (still **(lab: pending)**):

1. Apache (B1 row, B8: no `X-Forwarded-Proto` by default).
2. HAProxy `option forwardfor if-none`.
3. B6: nginx with no `X-Forwarded-For` directive.
4. B7: list mode with `127.0.0.1` when the proxy connects over `::1`; IPv4-mapped peers.
5. C1/C3: the shipped docker-compose file and Docker port publishing (iptables vs userland proxy).
6. D1-D4: Cloudflare modelled as an appending front; E1 is not reproducible locally.
7. §4: ingress-nginx straight to Nightscout; TCP without PROXY protocol; HTTP/HTTPS load-balancer modes; the
   log line when the ingress expects PROXY protocol and the load balancer does not send it.
8. `false` behind a proxy terminating TLS with `INSECURE_USE_HTTP=false` (redirect loop from §1 only).
9. Startup log lines in each state against §1.

## Sources

Listed per row above. General: [Express behind proxies](https://expressjs.com/en/guide/behind-proxies/),
[MDN X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Forwarded-For).
