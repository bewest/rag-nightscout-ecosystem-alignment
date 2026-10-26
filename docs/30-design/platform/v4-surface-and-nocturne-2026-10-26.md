# API v4: which parts to share with Nocturne, and which listener serves each

*Contributor-facing. Snapshot, 2026-10-26: alignment `main` `6e6223f26` (specifications),
cgm-remote-monitor draft PR #8857 at `3be98536`, Nocturne `main` `89dcaf1dd`. Every Nocturne
statement below was read from source at `89dcaf1dd` and nothing was run against it (read-derived).
The proposed surface is described in
[`specs/openapi/proposed/nightscout-v4.yaml`](../../../specs/openapi/proposed/nightscout-v4.yaml);
the current API in [`specs/openapi/upstream/cgm-remote-monitor/`](../../../specs/openapi/upstream/cgm-remote-monitor/README.md).
Nocturne paths are relative to `src/API/Nocturne.API/` unless they begin with `Core.` (under
`src/Core/Nocturne.`) or `tests/`. Nothing here has been sent to either project.*

The maintainer asked, on 2026-10-26, three things: how much of API v4 to unify with Nocturne, how
much is split by scope between the operator's and owner's listeners and the app listener, and
whether controller registration and instances belong on v4 endpoints. The maintainer's direction
the same day: Nocturne's v4 surface is to be split, and parts of it will sit on different
listeners. This page therefore treats Nocturne's surface as material to partition, group by group,
and states for each group which listener it belongs on in our specifications and whether it is a
candidate for a shared contract.

## 1. The answer in brief

- **Registration and instances on v4: yes, already.** The specifications put the product,
  definition and instance resources under the capability document's `submit.href`, and #8857 serves
  it at `/api/v4/registrations` (`lib/registration/index.js:25`); the command paths of commands §7.1
  are under `/api/v4/` too. Discovery stays at `/.well-known/nightscout/` (RFC 8615). What is not
  settled is the path the owner's actions take on `ns-tenant-admin` (§5, decisions 1–3).
- **Split by listener.** Of the 37 proposed operations, 26 are on the data listener, 10 on the
  tenant-owner listener, and one (retire) on both, by caller. None is on the operator listener:
  the operator's plane (tenant lifecycle, export) is not a v4 surface in our design (D7). Nocturne
  serves all three audiences from one API and divides them by scope and role (§4).
- **What to propose to Nocturne first:** discovery, the registration grammar with its product,
  definition and instance resources, the command and proposal paths, and statistics reads, all on
  the data listener. The owner's actions are shared as rules, not as a listener: each hub keeps its
  own way of refusing them to device and app credentials. Typed record and state-span paths come
  second, after the identity decisions. Everything else in Nocturne's v4 stays hub-specific (§6).

## 2. The proposed v4 surface, operation by operation

From [`nightscout-v4.yaml`](../../../specs/openapi/proposed/nightscout-v4.yaml). Listener names
follow [authority AU2](spec/authority.md#2-principals-and-credentials) (D16): `data` is `ns-api`
(devices, clients, viewers); `tenant-admin` is `ns-tenant-admin`, the owner's second bound socket
inside `ns-api`. Under `TENANCY_MODE=single` there is one listener and `API_SECRET` acts as the
owner. Status: `in-pr-8857` is served by #8857 at `3be98536` behind `CONTROLLER_REGISTRATION` (off
by default); `specified` has rules and conformance cases and no hub serves it; `open` is written
elsewhere in this repository with its placement undecided.

| # | operation | listener | credential | status | rules |
|---|---|---|---|---|---|
| 1 | `GET /.well-known/nightscout/sync` | data | none | in-pr-8857 | registration §4, CM31 |
| 2 | `GET /.well-known/nightscout/controllers` | data | none | in-pr-8857 | registration §2, registration §4, registration §16 Q2 |
| 3 | `GET /.well-known/nightscout/controllers/{kindId}` | data | none | in-pr-8857 | registration §2, registration §4 |
| 4 | `PUT /api/v4/registrations/{vendor}/{product}` | data | api:registrations:create, plus the binding to update | in-pr-8857 | registration §5.1, registration §5.2, registration §5.3, registration §5.4, AU4, authority §3, authority §5 |
| 5 | `GET /api/v4/registrations/{vendor}/{product}` | data | api:registrations:create | in-pr-8857 | registration §5.1, registration §5.4 |
| 6 | `DELETE /api/v4/registrations/{vendor}/{product}` | data and tenant-admin | api:registrations:delete and the binding (controller); the owner (tenant-admin) | in-pr-8857 | registration §5.1, registration §5.5, authority §4 |
| 7 | `PUT /api/v4/registrations/{vendor}/{product}/definitions/{definitionId}` | data | api:registrations:create and the product's binding | in-pr-8857 | registration §7, identity §2, D19 |
| 8 | `PUT /api/v4/registrations/{vendor}/{product}/instances/{instanceId}` | data | api:registrations:create; the instance's binding to renew | in-pr-8857 | registration §8, registration §9, registration §10, authority §3, authority §6, identity §2 |
| 9 | `DELETE /api/v4/registrations/{vendor}/{product}/instances/{instanceId}` | data | api:registrations:delete and the instance's binding | in-pr-8857 | registration §7, registration §8 |
| 10 | `GET /api/v4/registrations/instances` | tenant-admin | the tenant owner | in-pr-8857 | authority §4, authority §8, registration §8, registration §9 |
| 11 | `POST /api/v4/registrations/{vendor}/{product}/retire` | tenant-admin | the tenant owner | in-pr-8857 | authority §4, registration §5.5 |
| 12 | `POST /api/v4/registrations/{vendor}/{product}/block` | tenant-admin | the tenant owner | in-pr-8857 | authority §4, registration §5.1, registration §5.2 |
| 13 | `POST /api/v4/registrations/{vendor}/{product}/unblock` | tenant-admin | the tenant owner | in-pr-8857 | authority §4 |
| 14 | `POST /api/v4/registrations/{vendor}/{product}/release` | tenant-admin | the tenant owner | in-pr-8857 | authority §3, authority §4, authority §6 |
| 15 | `POST /api/v4/registrations/{vendor}/{product}/transfer` | tenant-admin | the tenant owner | in-pr-8857 | authority §3, authority §4, authority §6 |
| 16 | `POST /api/v4/registrations/{vendor}/{product}/free-namespaces` | tenant-admin | the tenant owner | in-pr-8857 | authority §4, authority §5, registration §5.5 |
| 17 | `POST /api/v4/registrations/{vendor}/{product}/transfer-role` | tenant-admin | the tenant owner | in-pr-8857 | authority §4, authority §6, registration §9 |
| 18 | `POST /api/v4/registrations/{vendor}/{product}/pin-version` | tenant-admin | the tenant owner | in-pr-8857 | authority §4, registration §12 |
| 19 | `POST /api/v4/registrations/{vendor}/{product}/unpin-version` | tenant-admin | the tenant owner | in-pr-8857 | authority §4, registration §12 |
| 20 | `POST /api/v4/commands` | data | api:commands:create | specified | CM1, CM2, CM3, CM4, CM5, CM6, CM30, CM32 |
| 21 | `GET /api/v4/commands` | data | api:commands:read or api:commands:create or api:proposals:read | specified | CM24, CM30, CM32 |
| 22 | `GET /api/v4/commands/{commandId}` | data | as the outstanding list (CM24) | specified | CM6, CM32 |
| 23 | `POST /api/v4/commands/{commandId}/cancel` | data | the sender, or the subject acting for the person | specified | CM25, CM26, CM32 |
| 24 | `POST /api/v4/commands/{commandId}/reports` | data | the destination instance's bound subject | specified | CM7, CM8, CM9, CM32 |
| 25 | `GET /api/v4/instances/{instanceId}/commands` | data | the instance's own bound subject | specified | CM18, CM26, CM31, CM32 |
| 26 | `POST /api/v4/proposals` | data | api:proposals:create and a propose role | specified | CM11, CM12, CM32 |
| 27 | `GET /api/v4/proposals/{proposalId}` | data | api:proposals:read or api:commands:create | specified | CM11, CM32 |
| 28 | `POST /api/v4/proposals/{proposalId}/approve` | data | api:commands:create | specified | CM13, CM14, CM15, CM22, CM30, CM32 |
| 29 | `POST /api/v4/proposals/{proposalId}/reject` | data | api:commands:create | specified | CM14, CM32 |
| 30 | `POST /api/v4/proposals/{proposalId}/withdraw` | data | the proposer, or the subject acting for the person | specified | CM14, CM32 |
| 31 | `POST /api/v4/proposals/{proposalId}/evaluations` | data | as reading the proposal | specified | CM16, CM11, CM32 |
| 32 | `GET /api/v4/statistics/daily` | data | read | open | REQ-STATS-001 |
| 33 | `GET /api/v4/statistics/daily/{date}` | data | read | open | REQ-STATS-001 |
| 34 | `GET /api/v4/statistics/summary` | data | read | open | REQ-STATS-002 |
| 35 | `GET /api/v4/statistics/hourly` | data | read | open | REQ-STATS-003 |
| 36 | `GET /api/v4/statistics/treatments` | data | read | open | REQ-STATS-004 |
| 37 | `GET /api/v4/statistics/current` | data | read | open | REQ-STATS-005 |

| status | data | tenant-admin | both | total |
|---|---|---|---|---|
| in-pr-8857 | 8 | 10 | 1 | 19 |
| specified | 12 | 0 | 0 | 12 |
| open | 6 | 0 | 0 | 6 |
| total | 26 | 10 | 1 | 37 |

**Notes on the table.**

- The commands specification names no listener for its paths. They are placed on the data
  listener because AU2 puts devices and clients there and none of CM1–CM32 is an owner action.
- Operations 1–3 are unauthenticated and carry no tenant data: the capability document is the
  same on every tenant host (registration §4).
- Operation 11 is #8857's form of the owner's retire; the specifications give it as `DELETE` on
  the product resource (operation 6). Operation 10's path is #8857's; authority §4 names the
  listing without a path.
- Operations 32–37 are from the [statistics API proposal](../../sdqctl-proposals/statistics-api-proposal.md)
  (REQ-STATS-001 to 005), which writes them at `/api/v3/stats/*`. §6.4 gives the evidence for
  placing them under v4.

**Defined without a path, so not in the OpenAPI file.** These are open:

| what | where it is defined | what is missing |
|---|---|---|
| typed record writes and reads | [registration §11](spec/registration.md#11-typed-writes-and-attribution) (an instance id on every typed write, "proposed as a request header"), [records](spec/records.md) R1–R9 | paths, the header's name, read and query forms |
| reading a definition or an instance | registration §7, §8 define `PUT` and `DELETE` only | whether `GET` exists for either |
| plan operations | [plans](spec/plans.md) PN1–PN18: propose a plan, approve in parts, report occurrences, skip, end, read the mirror | every path |
| marking the subject who acts for the person | [commands CM14, CM25](spec/commands.md#6-proposals-and-approvals-proposed) | who sets it, on which listener |
| the tenant-owner configuration surface | [tenant-owner surface §F.1](../tenancy/tenant-owner-config-surface-2026-09-15.md#f1-the-line): settings, plugin config, thresholds, subjects and roles, credential rotation, own export | every path; specified as a schema, not built |
| the operator's tenant lifecycle | [execution plan §2.3](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#23-design) (D7): create, list, get, suspend, activate, delete, export | built at `/tenants` on `bin/admin.js` on the seam chain, not on `dev`, and not a v4 path |
| the fetch-now subscription | [sync-transport T16](spec/sync-transport.md#5-typed-records-on-the-socket-proposed) | a socket event, not a REST path |

## 3. Nocturne's surface at `89dcaf1dd`, in groups

Nocturne's API project has 130 controllers outside its v1–v3 folders
(`src/API/Nocturne.API/Controllers/V4/**`, `Authentication/*`, `WellKnownController.cs`,
`MetadataController.cs`). A route-attribute parser counts 625 operations declared on them and 87
inherited from `V4CrudControllerBase` (nine per CRUD controller, nine controllers) and
`V4ReadOnlyControllerBase` (two per read-only controller, three), 712 in all. The parser and its
grouping are in the session's scratch and are not committed; the counts are read-derived.

Each group is mapped onto our specifications: **same concept, same shape**; **same concept,
different shape**; **Nocturne only**; and the two groups that are **ours only**.

| group | Nocturne controllers (paths) | ops | mapping | our counterpart |
|---|---|---|---|---|
| G1 discovery | `WellKnownController` (`/.well-known/openid-configuration`, `jwks.json`, `oauth-authorization-server`, `:57`, `:114`, `:142`), `MetadataController` (`/api/metadata/*`) | 11 | same concept, different shape | `/.well-known/nightscout/sync` and `/controllers` (operations 1–3) describe the sync contract; Nocturne's well-known documents describe its OAuth server |
| G2 sign-in and OAuth | `OAuthController` (`/api/oauth/*`, including RFC 7591 `POST /api/oauth/register`, `:983`), `Oidc`, `Passkey`, `Totp`, `DirectGrant`, `LoginHandoff` (`/api/auth/*`) | 50 | Nocturne only | none: devices hold a native per-tenant credential, people are to use Kratos (gated), and a delegated-access server is deferred (AU1, D17) |
| G3 typed records | `SensorGlucose`, `BGCheck`, `MeterGlucose`, `Calibration`, `Bolus`, `TempBasal`, `BasalInjection`, `Nutrition`, `Note`, `BolusCalculation`, `ApsSnapshot`, `PumpSnapshot`, `UploaderSnapshot`, `DeviceEvent`, health series, `Sleep`, `Battery`, `DeviceAge`, `Reservoir*`, `Foods`, `MealMatching` and others (24 controllers) | 182 | same concept, same shape | [records](spec/records.md) §3: its 16 primitives are Nocturne's V4 classes; our specifications give no paths (§2) |
| G4 state spans | `StateSpansController` (`/api/v4/state-spans`, `:37`) | 10 | same concept, different shape | [state and intent](spec/state-intent.md): measured differences in §6.2 (a cancel becomes a span of its own; units of applied durations), and Nocturne's `POST` reaches no controller (§7) |
| G5 profiles and therapy settings | `ProfileController`, `ProfileActivationsController`, `TimezoneTimelineController` (`/api/v4/profile`) | 38 | same concept, different shape | records R5: a controller-published, effective-dated `ControllerSettings` snapshot, where Nocturne's profile is held and edited at the hub |
| G6 statistics | `StatisticsController` (`/api/v4/statistics/*`, 30 operations) | 30 | same concept, different shape | the statistics API proposal (operations 32–37); §6.4 |
| G7 other analytics | `Analytics`, `Actogram`, `CgmComparison`, `ChartData`, `Correlation`, `CurrentTherapyState`, `DataOverview`, `LoopAnalysis`, `Prediction`, `Retrospective`, `SensorIntegrity`, `Summary`, `TreatmentLog`, `SleepReport` | 36 | Nocturne only | none |
| G8 alerts and notifications | `Alerts`, `AlertRules`, `AlertCustomSounds`, `AlertInvites`, `AlertReplay`, `DndWindows`, `Notifications`, `TenantAlertSettings`, `Trackers*` | 58 | Nocturne only | none in the specifications |
| G9 client devices | `ClientDevicesController` (`/api/v4/client-devices`) | 6 | same concept, different shape | instances (registration §8): both are a running app install that registers itself under a client-chosen id and refreshes on start (`ClientDevicesController.cs:42-53`, "idempotent upsert keyed on the install id"); Nocturne's is an alert actuation target (`:14-17`), ours a data source and command sink. Its `GET …/{id}/active-intents` "reconcile snapshot" (`:162-175`) and our fetch that returns a command until it is reported (CM26) answer the same reconnect question |
| G10 data sources and connectors | `Services` (`/api/v4/services`, data sources `:101-112`), `Configuration`, `ConnectorStatus`, `CareLinkConnect`, `WebhookSettings`, `GoogleHealth*`, `MyFitnessPalSettings` | 40 | same concept, different shape | the owner's listing (operation 10) says which instance wrote what; Nocturne lists data sources from the `DataSource` string each record carries (`IV4Record.cs:73`). Connector configuration: none in the specifications (nightscout-connect is a separate process) |
| G11 members, roles, sharing | `Role`, `MemberInvite`, `MembershipRequest`, `MemberRecovery`, `ShareLink`, `GuestLink`, `ChatIdentity*`, `LinkedPlatforms` | 48 | same concept, different shape | tenant-owner surface §F.1 ("their own subjects and roles"), no paths |
| G12 the signed-in person | `MyPermissions`, `MyTenants`, `Sessions`, `ConnectedApps`, `BackupSignInPrompt`, `Avatar`, `UserPreferences`, `CoachMark`, `RealtimeAdmission` (`/api/v4/me`, `/account`) | 20 | Nocturne only | none; a person's cross-tenant identity is D17 row 2 (Kratos, adopted in principle, gated) |
| G13 tenant settings and setup | `TenantSettings`, `TenantAppearance`, `SetupHub`, `Setup{Alerts,Devices,Therapy}`, `UISettings`, `ClockFaces*`, `GlucoseProcessingSettings`, `Setup` (`/api/v4/setup`, anonymous until set-up completes, `SetupController.cs:127`) | 54 | same concept, different shape | tenant-owner surface §B (the per-tenant settings census) and §E.1 (the first tenant is created by the operator with its root credential) |
| G14 tenant maintenance | `Migration`, `Deduplication`, `Discrepancy`, `NightscoutTransition`, `RejectedUploads`, `Compatibility`, `Audit` (most require `*`, `PermissionAttributes.cs:96`) | 31 | same concept, different shape | tenant-owner surface §F.1 (the owner reads and writes everything of their tenant); a record of owner actions is not kept (authority §8) |
| G15 platform administration | `Tenant` (`/api/v4/admin/tenants`, `TenantController.cs:14-16`), `TenantDirectGrant`, `AccessRequest`, `ConnectorAdmin`, `DatabaseCapacity`, `PlatformSettings`, `PlatformAccess`, `DemoAdmin`, `OidcProviderAdmin`, `SubjectAdmin` | 49 | same concept, different shape | D7: the operator's plane on its own entrypoint with no credential, unreachable from tenants (execution plan §2.2–§2.3) |
| G16 cross-tenant self-service | `PlatformController` (`/api/v4/platform/tenants`: list one's tenants, create one when `AllowSelfServiceCreation` is on, `:56-66`) | 3 | Nocturne only | none: tenant creation is the operator's (tenant-owner surface §F.1) |
| G17 hub information and catalogues | `Status`, `System`, `SystemEvents`, `Releases`, `Translations`, `Debug`, `Support`, `ContentContributions`, `DeviceCatalog`, `InsulinCatalog`, `TlsAuthorization` | 32 | Nocturne only | v1 `status.json` stays (sync-transport §7) |
| G18 demo and development | `DemoSession`, `DevOnly/*` | 14 | Nocturne only | none |
| ours: registration | — | — | ours only | operations 4–19. Nocturne's knowledge of each controller is compiled in (`IAidDetectionStrategy` and the V4 decomposers, [PROPOSAL-controller-descriptions §2.2](PROPOSAL-controller-descriptions-2026-09-11.md#22-two-halves-who-a-controller-is-and-what-its-data-means)) |
| ours: commands and proposals | — | — | ours only | operations 20–31. Nocturne's remote path is the legacy Loop notification (`ILoopService`, "1:1 legacy JavaScript compatibility", `Core.Contracts/Devices/ILoopService.cs:6`); `[RemoteCommand]` on its controllers is a client code-generation annotation (package `OpenApiRemoteCodegen.Attributes`), not a therapy command |

Mapping counts over Nocturne's 18 groups: same concept and same shape 1 (G3, 182 operations); same
concept and different shape 10 (G1, G4, G5, G6, G9, G10, G11, G13, G14, G15; 347 operations);
Nocturne only 7 (G2, G7, G8, G12, G16, G17, G18; 183 operations). Ours only: 2 groups (28
operations).

**One more shared mechanism, not an endpoint.** Our projected views for older readers
([registration §13](spec/registration.md#13-projected-views-for-older-readers)) and Nocturne's
`V4ToLegacyProjectionService` both serve v1–v3 reads from typed records. At `89dcaf1dd` "every
treatment read projects records of both provenances, since treatments have no legacy table left"
(`Services/V4/V4ToLegacyProjectionService.cs:29`); registration §13's note describes the
`NativeOnly` filter it read at `42275c812`. Our projected document carries `projectedFrom` and is
read-only; the specification's note that Nocturne's projected treatment carries no marker was read
at `42275c812` and was not re-checked here.

## 4. How each side divides the audiences

| audience | our specifications | Nocturne at `89dcaf1dd` |
|---|---|---|
| devices, uploaders, apps | the data listener with a native per-tenant credential (AU1); permissions are shiro strings, `api:<collection>:<action>`, and reading is one bit (AU5); the new names `api:registrations:*`, `api:commands:*`, `api:proposals:*` are proposals | the same API; OAuth clients registered by RFC 7591 hold category scopes in two tiers, `glucose.read` / `glucose.readwrite` and so on (`Core.Models/Authorization/Scope.cs:31-133`) |
| the tenant owner | its own listener, `ns-tenant-admin`; an owner action on the data listener with any other credential is 403 `not-authorised` (AU2); on `single`, `API_SECRET` | the same API; the tenant-administration atoms (`roles.manage`, `members.invite`, `members.manage`, `tenant.settings`, `sharing.manage`, `audit.read`, `audit.manage`, `Scope.cs:93-106`) are grantable to a member's role and are not requestable by an OAuth client: "there is no per-client scope ceiling to bound a request for them and no consent screen that could meaningfully describe them" (`Scope.cs:17-21`, sets at `:140`, `:171`, `:182`). Maintenance controllers require the full-access scope `*` (`Attributes/PermissionAttributes.cs:96`) |
| the operator | `ns-admin`, its own process and port, no credential, unreachable from tenants (D7, after ORY's public and admin ports) | the same API under `/api/v4/admin/*` with `[Authorize(Roles = "platform_admin")]`; the role is taken only from a credential that "is the person" (session, OIDC token, legacy JWT, platform-access token), never from a grant, API secret or OAuth token (`Core.Models/Authorization/PlatformAdminCredentials.cs:10-45`; `Middleware/AuthenticationMiddleware.cs:114-131`, `:151-154`). Server-to-server cross-tenant calls use `X-Instance-Key` only (`Attributes/RequireInstanceKeyAuthAttribute.cs:6-36`) |
| an anonymous viewer | none on v4 | public share links hold `reports.read`, so statistics compute calls are reachable without an account (`Extensions/ServiceRegistrationExtensions.cs:457-461`) |

**Where they agree.** Both refuse owner powers to a credential issued to a device or an app. Ours
does it by the listener the request arrives on (AU2); Nocturne's by keeping the owner atoms out of
the set an OAuth client may request (`Scope.cs:17-21`) and the operator role out of every delegated
credential (`PlatformAdminCredentials.cs`). Both keep the operator's powers out of every tenant
credential.

**Where they differ.** Ours separates audiences by socket; Nocturne by scope and role on one API.
A search of `src/API` for `Listen*`, `RequireHost` and `MapWhen` finds none; `Program.cs:81`
configures Kestrel only for the request body limit. Our operator plane has no credential at all;
Nocturne's operator is a person holding `platform_admin`. Our registration permissions are
collection-style strings; Nocturne's scopes are per data category, which is closer to the scoped
reads authority DR1 asks for.

**The consequence for a shared contract.** A rule written as "on `ns-tenant-admin`" cannot be met
by a hub with one listener. A rule written as "an owner action is refused to any credential a
device or app holds, with 403 `not-authorised`" is met by both: by AU2's listener, and by
Nocturne's atom partition. The conformance cases `owner-action-on-data-listener` and
`instances/owner-transfer-role-data-listener` already state the refusal; their `listener` member
is how a hub with listeners runs them.

## 5. Registration and instances on v4

**Decided.** D18 (two tiers: well-known and controller-owned), its addendum (the extensible
grammar), D19 (definitions and instances) and D20 (version-scoped quirks and the two-id rule), with
the maintainer's decisions of 2026-10-14 to 2026-10-17
([execution plan §2.6](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration));
the owner's actions on `ns-tenant-admin` and `API_SECRET` as owner on `single` (AU2, decided
2026-10-14 and 2026-10-16). The product resource is `<submit.href>/<vendor>/<product>`; the
capability document says where `submit.href` is.

**What #8857 serves at `3be98536`.** The capability document, the catalogue and each well-known
registration (`lib/registration/index.js:136-157`); the product resource, definitions and instances
under `/api/v4/registrations` (`lib/registration/products.js:266-289`); the owner's actions as
`POST …/<action>` (`:307-333`) with `retire` among them (`negotiate.js:742`); the owner's listing at
`GET /api/v4/registrations/instances` (`products.js:295`). The owner is recognised only as
`API_SECRET` (`products.js:313`), since no `ns-tenant-admin` exists. Its capability document
offers `submit` and `instances` and no `commands` (`index.js:93-107`).

**What Nocturne does.** It registers who an app is, not what its data means. `POST
/api/oauth/register` is RFC 7591 dynamic client registration: "Every call issues a new client"
(`Controllers/Authentication/OAuthController.cs:973-984`); a `software_id` names the app, and a
bundled directory of 12 known apps keyed on reverse-DNS `software_id` (`org.loopkit.loop`,
`org.nightscout.trio`, `info.nightscout.androidaps`, …) "provides the identity a dynamic
registration receives when its redirect URIs prove it is the app it names"
(`Core.Models/Authorization/KnownOAuthClients.cs:5-15`; matched at
`Services/Auth/OAuthClientService.cs:143`). What each controller's documents mean is compiled into
the server.

**Whether they compose.** They answer different questions and do not overlap: Nocturne's
registration says who is writing and with what scopes; ours says what the writes mean and which
copy wrote them. [PROPOSAL-controller-descriptions §2.2](PROPOSAL-controller-descriptions-2026-09-11.md#22-two-halves-who-a-controller-is-and-what-its-data-means)
proposes joining them on the reverse-DNS `software_id`. The grammar has not adopted it:
`controller-state-model.schema.json` `metadata` has `vendor`, `product`, `algorithmFamily`,
`versionRange`, `source` and `tier`, and no `softwareId`. Composed, a Nocturne client registered as
`org.loopkit.loop` would submit a registration whose `metadata` names the same id, and a hub could
read both halves from one key. On our side the binding is to the subject (AU4), which under
Nocturne's model would be the OAuth client's subject.

## 6. The proposed split, and what to propose to Nocturne first

### 6.1 Group, listener, shared or hub-specific

| group | listener in our design | shared or hub-specific | evidence |
|---|---|---|---|
| discovery (ours, operations 1–3) | data, unauthenticated | **shared** | about the software, not a person; same on every tenant (registration §4); cheap to serve beside Nocturne's own well-known documents |
| G1 Nocturne's OAuth metadata | data, unauthenticated | hub-specific | describes an authorization server our design defers (AU1, D17) |
| registration: product, definitions, instances (operations 4–9) | data | **shared** | specified with 186 conformance cases; the controller is a device on its native credential (authority §5) |
| registration: the owner's actions and listing (operations 10–19, and 6 for the owner) | tenant-admin; `API_SECRET` on `single` | **shared as rules, hub-specific as listener** | §4: the refusal to device and app credentials is common ground, the mechanism is not |
| commands and proposals (operations 20–31) | data | **shared** | specified (CM1–CM32); neither hub has a command record today (commands §8) |
| G6 statistics, reads over stored data | data, read | **shared** | maintainer, 2026-10-26: the statistics API proposals are likely to be accepted, which also separates statistics from the reports UI code; §6.4 |
| G6 statistics, compute over a posted body | data | hub-specific | a compute service over caller data, with its own cost bounds (§6.4) |
| G3 typed records | data | **shared, second** | records §3 is Nocturne's model; paths and the instance header wait on the identity decisions (§7) |
| G4 state spans | data | **shared, second** | the semantics differ on measured cases (state and intent §6.2); agree the rules first |
| G9 client devices | data | hub-specific | an alert target, not a data source; instances may later carry such a role as `{value: other}` (registration §9), not proposed here |
| G5 profiles; G7 analytics; G8 alerts (follower reads, acknowledge); G17 information; G18 demo | data | hub-specific | product features of each hub; no counterpart in the specifications |
| G8 alert rules and tenant alert settings; G10 connector configuration; G11 members, roles, sharing; G13 settings and setup; G14 maintenance | tenant-admin | hub-specific | the tenant-owner surface (§F.1) is per-hub configuration; its vocabulary is each hub's own (§B census) |
| G15 platform administration | operator | hub-specific | D7 |
| G2 sign-in and OAuth; G12 the signed-in person | open | hub-specific | depends on D17 row 2 (gated) and the deferred delegated-access server |
| G10 data-source listing; G16 self-service tenants | open | hub-specific | decisions 9 and 11 below |

### 6.2 The minimum shared v4 contract

1. **Discovery**: `GET /.well-known/nightscout/sync` and `/controllers`, with the capability
   document's schema.
2. **Registration**: the grammar (`controller-state-model.schema.json`), the product, definition
   and instance resources with their etag and precondition rules, the element results, and the
   fallback rule; the owner's actions as rules with the refusal stated per credential (§4).
3. **Commands**: the command record, the outstanding list, fetch and report, cancel, and the
   proposal in front of a command.
4. **Statistics**: reads over stored data, with a time-zone rule and a minimum-data rule (§6.4).

Second wave, after the decisions they depend on: typed record paths (G3) and state spans (G4).

### 6.3 Credit

The record catalogue is Nocturne's V4 model (records §3). The partition of scopes into what an
OAuth client may request and what a tenant role may confer (`Scope.cs:17-21`) is the closest prior
art for stating the owner boundary as a rule on credentials rather than on sockets; §4 proposes
exactly that. The reverse-DNS `software_id` directory is Nocturne's. The leases, labels and
selectors, the declared-versus-observed split and the resource-with-etag style are taken from
Kubernetes ([PROPOSAL-controller-descriptions §4](PROPOSAL-controller-descriptions-2026-09-11.md#4-what-the-proposal-is-and-what-it-takes-from-kubernetes));
the operator plane secured by unreachability is ORY's public and admin port split (D7).

### 6.4 Statistics

**Our two documents disagree.** The statistics API proposal (REQ-STATS-001 to 005) writes
`/api/v3/stats/{daily,daily/{date},summary,hourly,treatments,current}`; the reporting needs
analysis (GAP-REPORT-001, [`reporting-needs-analysis.md:203-212`](../../10-domain/reporting-needs-analysis.md))
lists `/api/v3/statistics/{tir,daily,a1c,agp}` and says it comes from the proposal. The proposal
also specifies an MCP resource provider on top (REQ-STATS-005;
[ECOSYSTEM-PROGRAMME](../../00-overview/ECOSYSTEM-PROGRAMME.md) "Statistics and agents").

**v3 or v4.** The recommendation is v4, `/api/v4/statistics/`, as the OpenAPI file places it:

- API v3 is a per-collection contract: its description is `/{collection}`, `/{collection}/{identifier}`
  and `/history` with `version`, `status` and `lastModified` beside them
  ([api-v3.yaml](../../../specs/openapi/upstream/cgm-remote-monitor/api-v3.yaml)), and cgm-remote-monitor
  mounts routes per enabled collection (`lib/api3/generic/collection.js:42-57`, collections listed
  at `lib/api3/index.js:66`). A documented client reading `/{collection}/{identifier}` would take
  `/api/v3/stats/daily` for a record of a collection called `stats`.
- Statistics are computed reads, like the other non-collection resources the specifications put
  under v4.
- Nocturne serves statistics at `/api/v4/statistics/` (`Controllers/V4/Analytics/StatisticsController.cs`, route `api/v4/[controller]`).
- Against: v3 already has non-collection routes (`/status`, `/version`, `/lastModified`), so v3
  could host them; the choice is open (decision 6).

**Why a server API now.** cgm-remote-monitor's reports compute in the browser: the report client
fetches raw entries and treatments over API v1 (`lib/report/reportclient.js:343`, `:380`, `:417`,
`:697`) and 14 plugin files of 6,169 lines compute from them, for example the A1c estimates and
quartiles in `lib/report_plugins/dailystats.js:126-130` and GVI in `glucosedistribution.js:524`,
using the statistics helpers in `lib/report/statistics.js` that six plugins import (all read at
#8857's `3be98536`). The proposal's 2026-05 status records that `tests/reports.test.js` was retired
on the assumption that statistics move to a server API, and asks for a parity test against the
plugin math.

**What a shared contract must settle that the proposal does not.** Read from Nocturne's tests:

| question | statistics API proposal | Nocturne at `89dcaf1dd` |
|---|---|---|
| which days and hours | not stated | buckets local days and hours on the tenant's zone; without a zone it withholds the day-dependent figures and says why (`tests/Unit/Nocturne.API.Tests/Controllers/V4/Analytics/StatisticsControllerTimeZoneTests.cs:83-437`, including the long daylight-saving day at `:285`) |
| too little data | not stated | a period with fewer than ten readings carries no figures (`StatisticsControllerAggregationTests.cs:75`) |
| which readings | not stated | the canonical stream across CGMs unless one device is named (`StatisticsController.cs:486-490`) |
| compute over posted data | not offered | `POST` actions compute over a caller-supplied body up to 100 MB (`StatisticsController.cs:55-60`), limited to 60 a minute per tenant host because public share links can reach them (`ServiceRegistrationExtensions.cs:457-472`), guarded by `StatisticsComputeLimitTests.cs:27-98` |
| who may read | `readable` | `reports.read`, held by public share links |
| caching | per-endpoint durations (proposal "Caching Strategy") | 60-second client cache on three `GET`s, five minutes server-side on `periods` (`StatisticsController.cs:34-36`) |

## 7. Open decisions for the maintainer

Each is a placement or a rule the evidence above does not settle.

| # | decision | evidence |
|---|---|---|
| 1 | **The owner's action paths on `ns-tenant-admin`.** The same path as on `single`, served on the other socket, or a separate admin prefix. | `registration-submit.schema.json` `request` says "`POST <admin registrations path>/<vendor>/<product>/<action>`"; the [hub-implementer guide §4.6](guides/hub-implementer.md#46-s5-the-owners-actions-on-single) and #8857 put them under the same router as the controller's (`/api/v4/registrations`). This is a mismatch between two of our texts. |
| 2 | **The owner's retire: `DELETE` or `POST …/retire`.** | registration §5.1 and the schema's `request` say `DELETE`; #8857 serves `POST …/retire` (`negotiate.js:742`). On `single`, one `API_SECRET` holder may be both the bound controller and the owner, so `DELETE` alone cannot tell which is acting. |
| 3 | **The owner's listing path.** | authority §4 gives none; #8857 uses `GET /api/v4/registrations/instances`. |
| 4 | **One root for instance paths.** | the instance is `/api/v4/registrations/{vendor}/{product}/instances/{instanceId}`; its command fetch is `/api/v4/instances/{instanceId}/commands` (commands §7.1). The capability document carries both, so it works either way. |
| 5 | **State the commands listener, and who marks the subject acting for the person.** | commands §7.1 names no listener; CM14 and CM25 rely on a mark no specification places. |
| 6 | **Statistics: v4 or v3; `stats` or `statistics`; `GET` over stored data only; the time-zone and minimum-data rules; the read credential.** | §6.4. |
| 7 | **Add `softwareId` to registration `metadata`.** | PROPOSAL-controller-descriptions §2.2; the grammar does not have it (§5). |
| 8 | **State the owner boundary per credential in the shared contract**, so a one-listener hub can conform. | §4. |
| 9 | **The data-source listing: data listener or owner's listener.** | Nocturne serves its data sources to `devices.read` on the data API (`ServicesController.cs:101-112`); our listing of instances, bindings and overlaps is the owner's (authority §4). |
| 10 | **Operator actions on a tenant member's credentials.** | Nocturne's operator can list and remove a member's passkeys and OIDC identities and issue login and recovery codes (`TenantController.cs:186-310`); tenant-owner surface §F.1 lists create, list, suspend, activate, delete and export for the operator. |
| 11 | **Self-service tenant creation.** | Nocturne allows it behind `AllowSelfServiceCreation` (`PlatformController.cs:56-66`); §F.1 makes tenant creation the operator's. |
| 12 | **Typed record paths: start from Nocturne's v4 routes or define our own.** | records §3 shares the model; the identity decisions (`ID-FORMAT-DECISION` and the others in the hub-implementer guide's backlog) decide how a typed write is matched and re-sent. Nocturne issue [#1932](https://github.com/nightscout/nocturne/issues/1932) (open) records that its v3 `POST` ignores a client's `identifier` and never upserts. |

## 8. How this was produced

- Our side: the specifications under [`spec/`](spec/), the JSON Schemas under `specs/sync/`, the
  tenancy execution plan and the tenant-owner surface, read at `6e6223f26`; #8857 read at
  `3be98536` in a read-only checkout.
- Nocturne: cloned at `89dcaf1dd` into a scratch directory; controllers parsed for `[Route]`,
  `[Http*]` and authorization attributes, then read by hand where a row above cites a line.
  Nocturne issue #2130 (open), "One record-changed seam instead of four write-notification
  mechanisms", bears on sync-transport T12 and is not used above.
- The OpenAPI file lints with 0 errors under `make openapi-lint` (Redocly CLI 1.34.0), which now
  includes `specs/openapi/proposed/`; a copy with one broken `$ref` fails with "Can't resolve
  $ref".
