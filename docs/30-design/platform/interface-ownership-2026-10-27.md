# Which interface owns which API: single-tenant and hosted multitenant

*Contributor-facing. Snapshot, 2026-10-27: cgm-remote-monitor dev `7abe1cf6`, with draft PRs read at
their heads (#8857 `f7a43fed`, #8865 `1dafe2a5`). Drafted by session -ee's research agent from the
sources listed below; two code claims re-checked by -ee (#8857's `INSTANCES_HREF`, #8865's `serve api`
mounts). Nothing here is decided beyond what its sources record; §5's questions are for the
maintainer. "Read" means read from the path given. "{C}" is the
[deployable components](../tenancy/nightscout-deployable-components-2026-09-14.md) document, "exec
plan" the [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md), "v4 doc"
the [v4 surface](v4-surface-and-nocturne-2026-10-26.md), "§F.1" the
[tenant-owner configuration surface](../tenancy/tenant-owner-config-surface-2026-09-15.md).*

**Summary.** On dev today one listener serves everything: API v1, v2 and v3, the socket.io channels,
the pages and, in #8857 behind a flag, `/.well-known` and `/api/v4`. `API_SECRET` is both the device
credential and the owner credential.

The decisions split hosted multitenant along two axes:
- **Audience** gives three listeners (D16): `ns-api` for the data path, `ns-tenant-admin` for the
  tenant owner, and `ns-admin` for the platform operator.
- **Workload** gives the roles `api`, `evaluator`, `realtime` and `vcpool` (D5).

D21 packages both as `nightscout serve <roles>`.

Most v1, v2, v3 and v4 data operations stay on the data listener. Owner actions and owner
configuration move to the tenant-owner listener. Tenant lifecycle exists only on the operator's
credential-free plane.

The sources leave several things unplaced or in conflict (§4):
- v1's hosted home;
- the socket's listener and its write events;
- the split of `/api/v2/authorization`;
- the pages;
- paths served on two listeners.

## 1. Interfaces at a glance

| interface | bind address | callers | credential | role / process |
|---|---|---|---|---|
| **single's one listener** | `HOSTNAME`/`PORT` (read: `lib/server/server.js:41-42,58`); socket.io on the same server (`:74`) | everyone | `API_SECRET` (grants `['*']`, exec plan §2.8), subject tokens, JWTs from the v2 exchange; configuration from `process.env` (D15) | `nightscout single` = `node lib/server/server.js` (D21 rule 1; #8865 `lib/cli/commands/single.js`) |
| **data / consumer, `ns-api`** | `API_HOSTNAME`/`API_PORT`, falling back to `HOSTNAME`/`PORT` (read: #8865 `lib/server/serve/listeners.js:8-11`) | uploaders, AID controllers, apps, followers, browsers | per-tenant root credential, per-tenant subject tokens, per-tenant JWT signing key; tenant resolved from Host before any credential is examined (D13, D14, AU3). No deployment secret | `serve api` (#8865; the only role that starts today) |
| **realtime socket, `ns-realtime`** | `REALTIME_HOSTNAME`/`REALTIME_PORT` (read: #8865 `roles.js:27-31`); not startable yet | browsers, followers, AndroidAPS 3.4.x's v1 socket (authority §9 item 7) | as data; checked at the `authorize` event (read: `websocket.js:142-160,1034`) | `serve realtime` (D5, D21); D16 puts it in the same audience row as `ns-api` |
| **tenant owner, `ns-tenant-admin`** | `TENANT_ADMIN_HOSTNAME`/`_PORT` (read: #8865 `roles.js:36-40`); decided 2026-10-16 as a second bound socket inside `ns-api` | the tenant owner; later caregivers | the tenant's own root credential today (§F.1); people through an interchangeable identity provider, with Nightscout's `nsjwt` exchange minting the per-tenant token (D17 row 2, gated; amended 2026-10-27) | `serve tenant-admin` in D21, or a socket in the `api` process per D16; listed in #8865, not startable |
| **platform operator, `ns-admin`** | default `127.0.0.1:1338`. A non-loopback bind is refused without `ADMIN_INSECURE_BIND_ACKNOWLEDGED=true`; the consumer address is refused on any port (read: #8865 `listeners.js:13-17`, `roles.js:41-46`; exec plan §2.3) | the hoster | none: secured by being unreachable (D7) | `serve admin` (D21), or `bin/admin.js` on the seam chain; on neither dev nor #8865 |
| **well-known discovery** | data listener, unauthenticated (v4 doc §2, operations 1–3) | controllers, at launch and after a release | none | in #8857, mounted only in single's `app.js` |
| `ns-evaluator`, `ns-vcpool` | no inbound listener | — | outbound only | `serve evaluator`, `serve vcpool` |

## 2. APIs by owner

State: **dev** (on `official/dev` `7abe1cf6`), **PR** (in a draft PR), **proposed** (specified, not served).

| API family | path prefix | single | multi | caller | credential | state | source |
|---|---|---|---|---|---|---|---|
| v1 records: entries, echo, times, slice, count, treatments, profile, devicestatus, notifications, activity, food | `/api/v1/…` | one | data | uploaders, controllers, apps, followers | `API_SECRET`, subject token or JWT; per-tenant under multi | dev; hosted: proposed | read `lib/api/index.js:147-166`; {C} §2.1 puts v1 CRUD in `ns-api`; #8865's `api` role does not serve v1 |
| v1 other: status, verifyauth, adminnotifies, experiments, alexa, googlehome; `/api/versions` | `/api/v1/…`, `/api` | one | not found | apps, the admin page | as v1 | dev | read `lib/api/index.js:162-176`, `lib/api/root.js:10` |
| v2 token exchange | `/api/v2/authorization/request/:token` | one | data | v3 clients, browser | access token → JWT | dev; PR #8865 | read `lib/authorization/endpoints.js:31`; #8865 `serve/api.js:35` |
| v2 subjects, roles, permissions | `/api/v2/authorization/{subjects,roles,permissions}` | one | **not stated** (§F.1 makes subjects and roles the owner's) | the `/admin` page | `admin:api:subjects:*`, `admin:api:roles:*` | dev | read `endpoints.js:41-112` |
| v2 ddata, properties, summary, notifications | `/api/v2/…` | one | data (summary as a query, {C} §2.1); ddata needs a resident `ddata` (ST-VIEWS, M4) | browser, followers | read permission | dev | read `lib/api2/index.js:14-19` |
| v3 generic, lastModified, version, status | `/api/v3/…` | one | data | AndroidAPS, xDrip+, apps | JWT | dev; PR #8865 | read `lib/api3/index.js:78-96` |
| v4 statistics | `/api/v4/statistics/…` | — | data | report readers | `reports.read` (mapping open, v4 doc §7 decision 6) | proposed | v4 doc operations 32–41 |
| v4 registration (controller) | `PUT`/`GET`/`DELETE /api/v4/registrations/{vendor}/{product}`, `PUT …/definitions/{id}` | one | data | controller | `api:registrations:create` and `:delete`, in the default `devicestatus-upload` role | PR #8857, `CONTROLLER_REGISTRATION` off by default | #8857 `products.js:284-331`, `authorization/storage.js:238`; v4 doc operations 4–7 |
| v4 instances (controller) | `PUT`/`DELETE /api/v4/instances/{id}` | one | data | controller | as registration, plus the instance's binding | PR #8857 | #8857 `index.js:28`, `products.js:360-374` |
| v4 owner actions | `POST /api/v4/registrations/{v}/{p}/{retire,block,unblock,release,transfer,free-namespaces,transfer-role,pin-version,unpin-version}` | one, `API_SECRET` | tenant-admin; 403 `not-authorised` on data | tenant owner | `API_SECRET` (single); tenant root credential or a token minted after identity-provider sign-in (multi) | PR #8857 | #8857 `products.js:302-330`; authority §4, AU2, AU6, AU7 |
| v4 owner listing | `GET /api/v4/instances` | one, `API_SECRET` | tenant-admin | tenant owner | owner only (`instances.js:668-669`) | PR #8857 | v4 doc §7 decision 3 |
| v4 commands and proposals | `/api/v4/commands…`, `GET /api/v4/instances/{id}/commands`, `/api/v4/proposals…` | one | data | senders, controllers, agents | `api:commands:*`, `api:proposals:*`, the instance's subject | proposed (not in #8857) | commands §7.1, CM32 |
| v4 data sources and connectors | no path | environment (`CONNECT_*`) | tenant-admin | tenant owner | owner | proposed, no path | v4 doc §7 decision 9 |
| owner configuration: settings, plugins, thresholds, subjects, rotation, own export, the acting-for-person mark | no path | `process.env` plus `/admin` | tenant-admin | tenant owner | tenant root credential | specified as a schema | §F.1; v4 doc §2; CM14 |
| tenant lifecycle and export | `/tenants` | — | `ns-admin` | hoster | none | seam chain, not dev | exec plan §2.3 |
| socket root namespace: `authorize`, `loadRetro`, `dataUpdate`, `retroUpdate`, `dbAdd`, `dbUpdate`, `dbUpdateUnset`, `dbRemove` | `/socket.io` | one | realtime | browsers, followers, AndroidAPS 3.4.x | `secret` or `token` at `authorize` | dev | read `websocket.js:421-1060` |
| socket `/storage`, `/alarm` namespaces | `/socket.io` | one | realtime | v3 clients, alarm clients | token | dev | read `api3/storageSocket.js:19`, `alarmSocket.js:21` |
| pages and static: `/`, `/admin`, `/food`, `/profile`, `/report`, `/split`, `/clock`, `/bundle`, swagger | `/…` | one | **not found** | browsers | pages are public; their actions use the APIs above | dev | read `lib/server/app.js:250-316` (careportal writes `/api/v1/treatments`; no route of its own) |
| well-known | `/.well-known/nightscout/{sync,controllers,controllers/{kind}}` | one, when `CONTROLLER_REGISTRATION` is on | data | controllers | none | PR #8857 | #8857 `index.js:18-28`, `env.js:133-140` |

## 3. What moves between single-tenant and multitenant, and why

1. **The credential root.** Under single-tenant, `API_SECRET` grants `['*']` and acts as the owner
   (AU2). Under multitenant no deployment secret exists on any interface (D13).
   - Each tenant holds its own root credential and signing key (D14).
   - Subject tokens are re-rooted on the tenant's credential, because today they hash `API_SECRET`
     (exec plan §2.8).
   - The reason: one install-wide secret and key cannot separate tenants. With per-tenant keys, a token
     presented to another tenant fails its signature check, not just a claim check.
2. **The configuration source.** `single` reads the environment; hosted roles read per-tenant
   configuration from the database (D15). That is why the tenant-owner listener exists: under
   single-tenant the environment is the owner's interface, and under multitenant that interface has to
   be an authenticated, row-scoped API. Which settings a tenant owns is the
   [census](../../60-research/tenancy/t30-census-dev-2026-10-27.md) (264 on dev).
3. **The owner's actions.** The paths stay the same; they move from "one listener plus `API_SECRET`" to
   `ns-tenant-admin` (authority §4). The boundary is stated per credential (AU7), so a hub with one
   listener can conform.
4. **The operator plane appears.** Single-tenant has no operator. Multitenant adds tenant lifecycle on a
   credential-free, unroutable listener (D7). No credential means nothing to phish, leak or reuse; the
   cost is one operational rule: that port is never routed.
5. **Workloads split.** Sockets move to `realtime`, alarms and plugins to `evaluator`, connectors to
   `vcpool`, and stateless HTTP stays in `api` (D5). The listener count is per deployment, not per
   tenant.

## 4. Gaps and contradictions

1. **The v4 doc is stale about #8857.** At `f7a43fed`, #8857 serves `GET /api/v4/instances`
   (`index.js:28`, `products.js:376`), and its test asserts that the older
   `GET /api/v4/registrations/instances` answers 404 (`tests/registration.instances.test.js:316-327`).
   The v4 doc still describes `3be98536` in §5, the §5.1 follow-up table and §7 row 3's evidence.
2. **One path prefix, two listeners.** `/api/v4/instances` takes `PUT` and `DELETE` on data and `GET` on
   tenant-admin, and `DELETE` on a product is on both listeners (v4 doc operation 6). Authority §4 says
   the listener, not the path, decides. But no routing table states which methods each listener
   mounts; #8857 mounts one router with an `isOwner` check (`products.js:307`).
3. **`/api/v2/authorization` mixes two audiences.** `request/:token` is data-path, while `subjects`,
   `roles` and `permissions` are owner configuration (§F.1). #8865 mounts the whole router on the
   consumer listener (`serve/api.js:35`), and no source splits it.
4. **The scope of `serve api`.** The three sources disagree, and none dates v1's hosted home:
   - D21's table says "express and storage", configured per tenant from the database.
   - {C} §2.1 says v3, v1, v2 summary, auth and tenant resolution.
   - #8865 serves only v3 and the v2 authorization router, reading the environment. v1 is absent
     until ST-V3-DECOUPLE (M3), which is also why 81 API v3 suites fail under `serve api`.
   - **Decided 2026-10-27 (maintainer):** `serve api` serves API v1, API v3, the v2 summary and
     authorization, and tenant resolution, as {C} §2.1 says. v1 joins once its storage paths run without the
     in-memory cache. The socket stays with the realtime role (question 3 below is unchanged). As a
     consequence, the 15 API v3 tests that write to a record created through API v1 keep running under
     `serve api`.
5. **The socket's listener and its writes.** The sources disagree on where the socket lives:
   - CM28 puts it "on the hub's existing listener".
   - D16 groups `ns-api` and `ns-realtime` in one row.
   - #8865 gives `realtime` its own `REALTIME_*` listener.
   D21 also says `realtime` makes "no storage writes", but the root namespace takes `dbAdd`, `dbUpdate`,
   `dbUpdateUnset` and `dbRemove` (`websocket.js:447-992`).
6. **The tenant-admin plane.** D16 decided "a second bound socket inside `ns-api`", and D21 lists
   `serve tenant-admin` as a role. #8865 still marks it plane `consumer` "until D16's third listener is
   designed" (`roles.js:9-10`), so no listener rule keeps it off the data listener's address. That
   comment is stale.
7. **Names.** Exec plan §2.3 uses `ADMIN_BIND`; #8865 uses `ADMIN_HOSTNAME`.
8. **The healthcheck.** D21 rule 5 names `nightscout healthcheck` as the image's healthcheck. #8862 ships
   no image `HEALTHCHECK`, by the maintainer's decision: a boot-error page must not be restarted away.
   D21's text is stale.
9. **Discovery when hosted.** The v4 doc puts well-known on the data listener, but #8857 mounts it only in
   single's `app.js`, and #8865's `api` app answers 404 to everything else. Whether
   `CONTROLLER_REGISTRATION` is per deployment or per tenant under D15: not found.
10. **The pages.** No source assigns `/`, `/admin`, `/profile`, `/food`, `/report` or `/clock` to a
    listener or role under multitenant. `/admin` is the owner's UI today, and it calls owner endpoints.
11. **Stale lines in the v4 doc.**
    - §1 says the owner's path "is not settled", while §0 and §7 record it as decided.
    - The §2 note says the commands specification names no listener, but CM32 now names the data
      listener.

## 5. Open questions for the maintainer

1. **Is a composed `serve` of every role part of the multitenant target (D21, open)?**
   - (a) A supported topology, tested in TEN-LAB.
   - (b) A small-hoster convenience only.

   *Recommended: (a) for `api,realtime,tenant-admin,evaluator`, with `admin` always in its own process,
   as exec plan §2.3 and §F.1 require. #8865 already keeps one listener per role, so composing roles
   changes processes, not boundaries. TEN-LAB runs both shapes.*
2. **Where do tenant-owner actions live under single-tenant?**
   - (a) As now: one listener, `API_SECRET`, the same paths, configuration from the environment.
   - (b) An optional `TENANT_ADMIN_PORT` under single-tenant.
   - (c) Credential-only (AU7), with no listener rule.

   *Recommended: (a). It is decided for registration (AU2) and keeps D1. Offer (b) only if self-hosters
   ask.*
3. **Is the socket part of the data listener, or its own realtime role?**
   - (a) The `ns-api` listener, as CM28 words it.
   - (b) Its own `REALTIME_*` listener, with the edge routing `/socket.io/` on the same public host.

   *Recommended: (b), as #8865 encodes. Amend CM28 to read "the hub's public host". Amend D21's
   realtime row: socket writes go through the storage interface in `realtime`, or are refused under
   multitenant with a stated status.*
4. **Where is the identity-provider adapter boundary (D17 as amended)?**
   - (a) An OIDC token contract (issuer, audience, key set) turned into a subject.
   - (b) A per-provider plugin (Kratos session check, Clerk session).
   - (c) An identity-aware proxy passing a signed header.

   *Recommended: (a) as the contract, with (b) only for Kratos, which the Ory proof measured. The
   adapter sits on the tenant-owner listener's exchange. Its output is a subject plus a
   `tenant_members` lookup, and `nsjwt` mints the per-tenant token (D14). The data listener never
   accepts provider credentials (AU1). Owed: the list of properties each hoster must supply.*
5. **Should `/api/v2/authorization` be split under multitenant?**
   - (a) `request/:token` on data; `subjects`, `roles` and `permissions` on tenant-admin.
   - (b) Whole, on data, guarded by permissions.

   *Recommended: (a), following §F.1 and AU7. Single-tenant is unchanged.*
6. **How are paths served on two listeners routed?**
   - (a) A per-operation listener table generated from `nightscout-v4.yaml`, mounted on both listeners,
     with the data listener answering 403 `not-authorised` to owner operations. The conformance cases
     `owner-action-on-data-listener` and `instances/owner-transfer-role-data-listener` exist.
   - (b) A separate owner prefix.

   *Recommended: (a). The same paths on every deployment is decided (v4 doc §7 decision 1).*
7. **Where and when does v1 go hosted?**
   - (a) Into `serve api` after ST-V3-DECOUPLE (M3).
   - (b) A separate `v1` role.
   - (c) No v1 under multitenant.

   *Recommended: (a), since {C} §2.1 already assigns it there. The multitenant preview needs it: the
   apps in authority §9 item 7 authenticate with the hashed `api-secret` header.*
8. **Which of today's credential forms are accepted under multitenant (authority §9 item 7)?**
   - (a) The tenant's root credential, in today's hashed `api-secret` header and the v1 socket
     `secret`.
   - (b) New token forms only.

   *Recommended: (a), so uploaders need no change (D1), with subject tokens re-rooted per D13.*
