# API v4: which parts to share with Nocturne, and which listener serves each

*Contributor-facing. Snapshot, 2026-10-26: alignment `main` `6e6223f26` (specifications; amended
the same day for the maintainer's decisions in §0),
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

## 0. Decided, 2026-10-26

The maintainer decided four points the same day, and seven more in a second round (decisions 1, 2,
5, 8, 9, 10 and 11 in §7); the sections below are amended for them.

| point | decision | where it is applied |
|---|---|---|
| statistics | served on v4 under `statistics` (`/api/v4/statistics/...`), matching Nocturne `89dcaf1dd`'s `StatisticsController` for hub compatibility: its paths, parameters, response shapes, tenant time-zone bucketing, the under-ten-readings rule and its read scopes. The design stays open for discussion: what a shared contract fixes and what it leaves to each hub, and whether the compute-over-a-posted-body actions join later | operations 32–41; `specs/openapi/proposed/statistics-v4.schema.json`; §6.4; dated notes on the two older texts |
| registration scope | registration of products, definitions and instances is a per-tenant API that affects only that tenant's site and data, never a platform or operator action; the owner's listing and actions are tenant-scoped (tenant-admin under `multi`, the one listener under `single`); controller actions and commands are on the data listener | [authority AU6](spec/authority.md#2-principals-and-credentials); registration's opening note |
| instance paths | one flat root: `/api/v4/instances/{instanceId}` is the instance resource, its command fetch `/api/v4/instances/{instanceId}/commands`, and the owner's listing `GET /api/v4/instances`; creating an instance names the product in the body | [registration §7](spec/registration.md#7-definitions) amendment; commands §7.1; the instance schema's `product`; operations 8–10; §5.1 |
| `softwareId` | proposed in the registration's `metadata`, in Nocturne's RFC 7591 `software_id` form, for compatibility; its rules stay open for discussion | `controller-state-model.schema.json`; [registration §5.1](spec/registration.md#51-identity-and-methods); §5 |
| owner paths (1) | a controller registers with the credential it already holds: the role a hub issues by default to a device or uploader credential includes `api:registrations:create` and `:delete`, and the owner may withhold them. The owner's actions are for exceptions and use the same paths on every deployment (`/api/v4/registrations/…/<action>`, `/api/v4/instances`), on tenant-admin under `multi` and the one listener under `single` | [authority §4, §5](spec/authority.md#4-the-owners-actions); [registration §5.1](spec/registration.md#51-identity-and-methods); `registration-submit.schema.json` `request` |
| retire (2) | both: the bound controller retires with `DELETE` on the product, the owner with `POST …/retire`, as #8857 serves them | registration §5.1, §5.5; operations 6 and 11 |
| commands (5) | on the data listener; the tenant owner marks the subject acting for the person, as subject configuration on the owner's listener, and the hub reads the mark; a client cannot assert it | [commands CM14, CM32](spec/commands.md#6-proposals-and-approvals-proposed) |
| owner boundary (8) | stated per credential: an owner action is refused to any credential issued to a device or an app; a separate listener is one way to meet it. To be reviewed as the design matures | [authority AU7](spec/authority.md#2-principals-and-credentials) |
| data sources and connectors (9) | on the owner's listener: configuring a vendor cloud connection, triggering a sync and listing who sends data change or describe the runtime and its resources, unlike an AID controller's registration | §6.1 |
| operator and self-service (10, 11) | both hub-specific, outside the shared contract; in cgm-remote-monitor the operator keeps D7's tenant lifecycle with no access to members' credentials, and creating tenants stays the operator's. Revisit once D17 row 2 lands | §6.1 |

## 1. The answer in brief

- **Registration and instances on v4: yes, already.** The specifications put the product,
  definition and instance resources under the capability document's `submit.href`, and #8857 serves
  it at `/api/v4/registrations` (`lib/registration/index.js:25`); the command paths of commands §7.1
  are under `/api/v4/` too, and instances have their own flat root (§0). Registration is per tenant
  (AU6). Discovery stays at `/.well-known/nightscout/` (RFC 8615). What is not settled is the path
  the owner's actions take on `ns-tenant-admin` (§7, decisions 1–2).
- **Split by listener.** Of the 41 proposed operations, 30 are on the data listener, 10 on the
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
by default); `specified` has rules and conformance cases, or a decision of the maintainer, and
cgm-remote-monitor does not serve it.

| # | operation | listener | credential | status | rules |
|---|---|---|---|---|---|
| 1 | `GET /.well-known/nightscout/sync` | data | none | in-pr-8857 | registration §4, CM31 |
| 2 | `GET /.well-known/nightscout/controllers` | data | none | in-pr-8857 | registration §2, registration §4, registration §16 Q2 |
| 3 | `GET /.well-known/nightscout/controllers/{kindId}` | data | none | in-pr-8857 | registration §2, registration §4 |
| 4 | `PUT /api/v4/registrations/{vendor}/{product}` | data | api:registrations:create, plus the binding to update | in-pr-8857 | registration §5.1, registration §5.2, registration §5.3, registration §5.4, AU4, authority §3, authority §5 |
| 5 | `GET /api/v4/registrations/{vendor}/{product}` | data | api:registrations:create | in-pr-8857 | registration §5.1, registration §5.4 |
| 6 | `DELETE /api/v4/registrations/{vendor}/{product}` | data and tenant-admin | api:registrations:delete and the binding (controller); the owner (tenant-admin) | in-pr-8857 | registration §5.1, registration §5.5, authority §4 |
| 7 | `PUT /api/v4/registrations/{vendor}/{product}/definitions/{definitionId}` | data | api:registrations:create and the product's binding | in-pr-8857 | registration §7, identity §2, D19 |
| 8 | `PUT /api/v4/instances/{instanceId}` | data | api:registrations:create; the instance's binding to renew | specified | registration §7, registration §8, registration §9, registration §10, authority §3, authority §6, identity §2 |
| 9 | `DELETE /api/v4/instances/{instanceId}` | data | api:registrations:delete and the instance's binding | specified | registration §7, registration §8 |
| 10 | `GET /api/v4/instances` | tenant-admin | the tenant owner | specified | authority §4, authority §8, AU6, registration §8, registration §9 |
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
| 32 | `GET /api/v4/statistics/range-analytics` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:464` |
| 33 | `GET /api/v4/statistics/weekday-averages` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:532` |
| 34 | `GET /api/v4/statistics/hourly-patterns` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:567` |
| 35 | `GET /api/v4/statistics/periods` | data | glucose.read or reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:806` |
| 36 | `GET /api/v4/statistics/daily-basal-bolus-ratios` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:940` |
| 37 | `GET /api/v4/statistics/punch-card` | data | glucose.read or reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:988` |
| 38 | `GET /api/v4/statistics/insulin-delivery-stats` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:1039` |
| 39 | `GET /api/v4/statistics/basal-analysis` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:1081` |
| 40 | `GET /api/v4/statistics/hourly-insulin-delivery` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:1127` |
| 41 | `GET /api/v4/statistics/aid-system-metrics` | data | reports.read | specified | maintainer 2026-10-26; Nocturne `StatisticsController.cs:1188` |

| status | data | tenant-admin | both | total |
|---|---|---|---|---|
| in-pr-8857 | 6 | 9 | 1 | 16 |
| specified | 24 | 1 | 0 | 25 |
| total | 30 | 10 | 1 | 41 |

Three operations #8857 serves moved to `specified` with the flat instance root: #8857 serves them
at `PUT` and `DELETE /api/v4/registrations/{vendor}/{product}/instances/{instanceId}` and
`GET /api/v4/registrations/instances` (`lib/registration/products.js:283`, `:289`, `:295`).

**Notes on the table.**

- The commands specification names no listener for its paths. They are placed on the data
  listener because AU2 puts devices and clients there and none of CM1–CM32 is an owner action.
- Operations 1–3 are unauthenticated and carry no tenant data: the capability document is the
  same on every tenant host (registration §4).
- Operation 11 is #8857's form of the owner's retire; the specifications give it as `DELETE` on
  the product resource (operation 6). Operation 10's path follows the flat instance root (§0).
- Operations 32–41 are Nocturne's ten statistics reads over stored data, by the maintainer's
  decision (§0, §6.4). Their response shapes are in
  [`statistics-v4.schema.json`](../../../specs/openapi/proposed/statistics-v4.schema.json), read from
  Nocturne's models.

**Defined without a path, so not in the OpenAPI file.** These are open:

| what | where it is defined | what is missing |
|---|---|---|
| typed record writes and reads | [registration §11](spec/registration.md#11-typed-writes-and-attribution) (an instance id on every typed write, "proposed as a request header"), [records](spec/records.md) R1–R9 | paths, the header's name, read and query forms |
| reading a definition or an instance | registration §7, §8 define `PUT` and `DELETE` only (and the owner's listing) | whether `GET` exists for either |
| plan operations | [plans](spec/plans.md) PN1–PN18: propose a plan, approve in parts, report occurrences, skip, end, read the mirror | every path |
| marking the subject who acts for the person | [commands CM14, CM25](spec/commands.md#6-proposals-and-approvals-proposed) | the owner sets it (decision 5); the path for setting it is part of the tenant-owner configuration surface, not yet given |
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
| G6 statistics | `StatisticsController` (`/api/v4/statistics/*`, 30 operations) | 30 | same concept, same shape (by decision, 2026-10-26) | operations 32–41 follow its ten reads over stored data; §6.4 |
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

Mapping counts over Nocturne's 18 groups: same concept and same shape 2 (G3, and G6 by the
statistics decision; 212 operations); same concept and different shape 9 (G1, G4, G5, G9, G10,
G11, G13, G14, G15; 317 operations);
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
capability document says where `submit.href` is. On 2026-10-26 the maintainer decided that
registration is per tenant and never an operator action (AU6), and that instances have one flat
root, `/api/v4/instances/{instanceId}` (registration §7 amendment).

**What #8857 serves at `3be98536`.** The capability document, the catalogue and each well-known
registration (`lib/registration/index.js:136-157`); the product resource, definitions and instances
under `/api/v4/registrations` (`lib/registration/products.js:266-289`), instances nested under the
product (`:283`, `:289`), which the flat-root decision changes (§5.1); the owner's actions as
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
proposes joining them on the reverse-DNS `software_id`. On 2026-10-26 the maintainer decided to
propose it in Nocturne's form for compatibility: `metadata.softwareId` is now in
`controller-state-model.schema.json`, marked proposed, optional, compared exactly as Nocturne's
directory lookup compares it (`KnownOAuthClients.cs:214-215`), and not part of the registration's
identity ([registration §5.1](spec/registration.md#51-identity-and-methods)). Nocturne's
registration request carries it as `software_id` with no format check
(`Models/OAuth/ClientRegistrationRequest.cs:41-44`). Composed, a Nocturne client registered as
`org.loopkit.loop` would submit a registration whose `metadata` names the same id, and a hub could
read both halves from one key. On our side the binding is to the subject (AU4), which under
Nocturne's model would be the OAuth client's subject. Open for discussion: whether two products
may share one `softwareId`, and whether a hub checks it against the credential's registered client.

### 5.1 Are registrations and instances redundant?

The maintainer asked whether registrations and instances are redundant, or whether one is for the
kind and the other for the running copy, and if redundant whether one should go. They are not
redundant ([registration §7–§8](spec/registration.md#7-definitions), D19):

| resource | says | identity | lifetime |
|---|---|---|---|
| product registration, with its immutable definitions | what a controller's data means: the kind, per vendor and product, per release | `(vendor, product)`; each definition by the hash of its content | as long as the controller publishes it; definitions are never changed |
| instance | which running copy is connected: its definition, its roles on channels (source of record, command sink), its labels | a random UUID v4 the copy generates once | a lease the copy renews; a lapsed instance holds no roles |

Several instances run one definition (a phone and a lab rig, or the old and the new phone during a
migration), and one instance is the destination of commands for a channel. Removing either loses
something: without the product there is nothing to say what the writes mean; without instances
there is no way to tell two copies apart or to route a command to one.

The wrinkle was two path roots for one instance. Options considered:

| option | form | evidence |
|---|---|---|
| (a) keep both roots | `/api/v4/registrations/{vendor}/{product}/instances/{id}`, fetch at `/api/v4/instances/{id}/commands` | `commands.fetch` is a URI template in the capability document, so clients do not hard-code it; #8857 serves the nested form |
| (b) nest the fetch under the product | `…/{vendor}/{product}/instances/{id}/commands` | every fetch would carry the vendor and product, which the fetch rules (CM18, CM26) never use |
| (c) one flat root | `/api/v4/instances/{id}` and `/api/v4/instances/{id}/commands` | an instance id is a random UUID v4 (identity §2), so it names one copy without its product; the copy keeps one path for its life |

**Decided, maintainer 2026-10-26: (c).** Creating an instance names the product in the body
(`product: {vendor, product}` in `controller-instance.schema.json`), not by a create on the product
resource that answers with a flat `Location`. The evidence for the body: the instance id is chosen by
the controller and the create is a `PUT` to it (registration §8), so create, renew and release use
one path with no redirect; the order of checks already reads the product's registration, binding,
block and retirement for every `PUT`, and the stored instance and the owner's listing already carry
`vendor` and `product` (`registration-submit.schema.json` `storedInstance.identity`,
`instanceSummary`); and the conformance cases model an instance request with its `identity`
separately from the path, so none changes. A renewal naming another product is 422
`invalid-instance`. Nocturne has no instance resource; the nearest, its client devices, is flat:
`/api/v4/client-devices/{id}` (`ClientDevicesController.cs:21`, `:127`, `:150`).

**The follow-up for #8857.** Its routes at `3be98536` that change:

| #8857 today | after the decision |
|---|---|
| `PUT /api/v4/registrations/:vendor/:product/instances/:instanceId` (`lib/registration/products.js:283`) | `PUT /api/v4/instances/:instanceId`, product from the body's `product` |
| `DELETE /api/v4/registrations/:vendor/:product/instances/:instanceId` (`:289`) | `DELETE /api/v4/instances/:instanceId` |
| `GET /api/v4/registrations/instances` (`:295`) | `GET /api/v4/instances` (the owner's listing) |
| `lib/registration/schemas/controller-instance.schema.json` (vendored) | refreshed from `specs/sync/controller-instance.schema.json`, which gains `product` |

## 6. The proposed split, and what to propose to Nocturne first

### 6.1 Group, listener, shared or hub-specific

| group | listener in our design | shared or hub-specific | evidence |
|---|---|---|---|
| discovery (ours, operations 1–3) | data, unauthenticated | **shared** | about the software, not a person; same on every tenant (registration §4); cheap to serve beside Nocturne's own well-known documents |
| G1 Nocturne's OAuth metadata | data, unauthenticated | hub-specific | describes an authorization server our design defers (AU1, D17) |
| registration: product, definitions, instances (operations 4–9) | data | **shared** | specified with 186 conformance cases; the controller is a device on its native credential (authority §5); per tenant (AU6) |
| registration: the owner's actions and listing (operations 10–19, and 6 for the owner) | tenant-admin; `API_SECRET` on `single` | **shared as rules, hub-specific as listener** | §4: the refusal to device and app credentials is common ground, the mechanism is not; tenant-scoped, never operator (AU6) |
| commands and proposals (operations 20–31) | data | **shared** | specified (CM1–CM32); neither hub has a command record today (commands §8) |
| G6 statistics, reads over stored data | data, read | **shared** | decided, maintainer 2026-10-26: match Nocturne's reads; also separates statistics from the reports UI code; §6.4 |
| G6 statistics, compute over a posted body, and the stateless calculators | data | hub-specific for now | open for discussion whether they join later (§6.4) |
| G3 typed records | data | **shared, second** | records §3 is Nocturne's model; paths and the instance header wait on the identity decisions (§7) |
| G4 state spans | data | **shared, second** | the semantics differ on measured cases (state and intent §6.2); agree the rules first |
| G9 client devices | data | hub-specific | an alert target, not a data source; instances may later carry such a role as `{value: other}` (registration §9), not proposed here |
| G5 profiles; G7 analytics; G8 alerts (follower reads, acknowledge); G17 information; G18 demo | data | hub-specific | product features of each hub; no counterpart in the specifications |
| G8 alert rules and tenant alert settings; G10 connector configuration, sync and the data-source listing (decision 9); G11 members, roles, sharing; G13 settings and setup; G14 maintenance | tenant-admin | hub-specific | the tenant-owner surface (§F.1) is per-hub configuration; its vocabulary is each hub's own (§B census) |
| G15 platform administration | operator | hub-specific | D7 |
| G2 sign-in and OAuth; G12 the signed-in person | open | hub-specific | depends on D17 row 2 (gated) and the deferred delegated-access server |
| G16 self-service tenants; Nocturne's operator actions on members' credentials | operator, where a hub offers them | hub-specific | decisions 10 and 11 (§0) |

### 6.2 The minimum shared v4 contract

1. **Discovery**: `GET /.well-known/nightscout/sync` and `/controllers`, with the capability
   document's schema.
2. **Registration**: the grammar (`controller-state-model.schema.json`), the product, definition
   and instance resources with their etag and precondition rules, the element results, and the
   fallback rule; the owner's actions as rules with the refusal stated per credential (§4).
3. **Commands**: the command record, the outstanding list, fetch and report, cancel, and the
   proposal in front of a command.
4. **Statistics**: Nocturne's ten reads over stored data, with its time-zone and minimum-data rules
   and read scopes (decided, §6.4).

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

**Decided, maintainer 2026-10-26.** Statistics are on v4 under `statistics`, matching Nocturne
`89dcaf1dd`'s `StatisticsController` for hub compatibility: its paths, parameters, response shapes,
time-zone bucketing, the under-ten-readings rule and its read scopes. The OpenAPI file has its ten
`GET` reads over stored data (operations 32–41, anchored per operation to
`Controllers/V4/Analytics/StatisticsController.cs`), with response shapes read from Nocturne's
models into [`statistics-v4.schema.json`](../../../specs/openapi/proposed/statistics-v4.schema.json)
(83 types; read-derived from property declarations, nested types not checked by hand). Not
included: its 15 `POST` actions that compute over a posted body, and its five stateless calculators
(`gmi/{meanGlucose}`, `estimated-a1c/{averageGlucose}`, `clinical-targets/{population}`, and the two
unit conversions).

**Its read rule.** Each read is admitted on `reports.read`; `periods` and `punch-card` on
`glucose.read` or `reports.read`, and a response that merges categories is narrowed to the
caller's: insulin and carb aggregates need `reports.read` or `treatments.read`
(`Authorization/AnalyticsReadScopeGuards.cs:314-331`). Public share links hold `reports.read`.
cgm-remote-monitor has no such scopes: reading is one bit, `readable` (AU5), so how these map onto
its permissions is part of the open design.

**Open for discussion** (maintainer, 2026-10-26): what a shared contract should fix and what it
leaves to each hub (for example the population default, the canonical-stream choice across CGMs,
caching), and whether the compute-over-a-posted-body actions join later.

**The two older texts.** The statistics API proposal (REQ-STATS-001 to 005) wrote
`/api/v3/stats/{daily,daily/{date},summary,hourly,treatments,current}`, and the reporting needs
analysis (GAP-REPORT-001) `/api/v3/statistics/{tir,daily,a1c,agp}`. Both now carry a dated note
pointing at this decision and are otherwise unchanged. The proposal's MCP resource provider
(REQ-STATS-005; [ECOSYSTEM-PROGRAMME](../../00-overview/ECOSYSTEM-PROGRAMME.md) "Statistics and
agents") would sit on top of the v4 reads.

**Why v4 rather than v3**, the evidence before the decision: API v3 is a per-collection contract
(`/{collection}`, `/{collection}/{identifier}`, `/history`, with `version`, `status` and
`lastModified` beside them, [api-v3.yaml](../../../specs/openapi/upstream/cgm-remote-monitor/api-v3.yaml)),
mounted per enabled collection (`lib/api3/generic/collection.js:42-57`, `lib/api3/index.js:66`), so
a documented client would read `/api/v3/stats/daily` as a record of a collection `stats`; and
Nocturne already serves statistics under v4.

**Why a server API now.** cgm-remote-monitor's reports compute in the browser: the report client
fetches raw entries and treatments over API v1 (`lib/report/reportclient.js:343`, `:380`, `:417`,
`:697`) and 14 plugin files of 6,169 lines compute from them, for example the A1c estimates and
quartiles in `lib/report_plugins/dailystats.js:126-130` and GVI in `glucosedistribution.js:524`,
using the statistics helpers in `lib/report/statistics.js` that six plugins import (all read at
#8857's `3be98536`). The proposal's 2026-05 status records that `tests/reports.test.js` was retired
on the assumption that statistics move to a server API, and asks for a parity test against the
plugin math.

**The rules the decision adopts, and how the older proposal compared.** Read from Nocturne's tests:

| question | statistics API proposal | Nocturne at `89dcaf1dd` |
|---|---|---|
| which days and hours | not stated | buckets local days and hours on the tenant's zone; without a zone it withholds the day-dependent figures and says why (`tests/Unit/Nocturne.API.Tests/Controllers/V4/Analytics/StatisticsControllerTimeZoneTests.cs:83-437`, including the long daylight-saving day at `:285`) |
| too little data | not stated | a period with fewer than ten readings carries no figures (`StatisticsControllerAggregationTests.cs:75`) |
| which readings | not stated | the canonical stream across CGMs unless one device is named (`StatisticsController.cs:486-490`) |
| compute over posted data | not offered | `POST` actions compute over a caller-supplied body up to 100 MB (`StatisticsController.cs:55-60`), limited to 60 a minute per tenant host because public share links can reach them (`ServiceRegistrationExtensions.cs:457-472`), guarded by `StatisticsComputeLimitTests.cs:27-98` |
| who may read | `readable` | `reports.read`, held by public share links |
| caching | per-endpoint durations (proposal "Caching Strategy") | 60-second client cache on three `GET`s, five minutes server-side on `periods` (`StatisticsController.cs:34-36`) |

## 7. Open decisions for the maintainer

Each is a placement or a rule the evidence above does not settle. All but row 12 were decided on
2026-10-26 and keep their numbers; what remains open in them is stated.

| # | decision | evidence |
|---|---|---|
| 1 | **The owner's action paths on `ns-tenant-admin`.** *Decided, maintainer 2026-10-26:* the same paths on every deployment, served on the owner's listener; and a controller registers with the credential it already holds (the default device or uploader role includes the registration permissions; the owner may withhold them), so setting up a controller needs no owner action. | `registration-submit.schema.json` `request` says "`POST <admin registrations path>/<vendor>/<product>/<action>`"; the [hub-implementer guide §4.6](guides/hub-implementer.md#46-s5-the-owners-actions-on-single) and #8857 put them under the same router as the controller's (`/api/v4/registrations`). This was a mismatch between two of our texts; the schema text now names the controller's paths. |
| 2 | **The owner's retire: `DELETE` or `POST …/retire`.** *Decided, maintainer 2026-10-26:* both, as #8857 serves them: `DELETE` for the bound controller, `POST …/retire` for the owner. | registration §5.1 and the schema's `request` say `DELETE`; #8857 serves `POST …/retire` (`negotiate.js:742`). On `single`, one `API_SECRET` holder may be both the bound controller and the owner, so `DELETE` alone cannot tell which is acting. |
| 3 | **The owner's listing path.** *Decided, maintainer 2026-10-26:* `GET /api/v4/instances`, tenant-scoped (AU6), on tenant-admin under `multi` and the one listener under `single`. | registration is per tenant (AU6); the flat instance root (§5.1). #8857 serves `GET /api/v4/registrations/instances`. |
| 4 | **One root for instance paths.** *Decided, maintainer 2026-10-26: one flat root,* `/api/v4/instances/{instanceId}`, the product named in the body. | §5.1, with the #8857 follow-up. |
| 5 | **State the commands listener, and who marks the subject acting for the person.** *Decided, maintainer 2026-10-26:* the data listener; the tenant owner sets the mark as subject configuration, and the hub reads it. Open: whether more than one subject may hold it. | commands §7.1 names no listener; CM14 and CM25 rely on a mark no specification places. |
| 6 | **Statistics.** *Decided, maintainer 2026-10-26:* v4, `statistics`, matching Nocturne's reads. Open for discussion: what the shared contract fixes and what each hub keeps; whether compute over a posted body joins later; how `reports.read` maps onto cgm-remote-monitor's permissions. | §6.4. |
| 7 | **`softwareId` in registration `metadata`.** *Decided, maintainer 2026-10-26:* proposed, in Nocturne's `software_id` form. Open for discussion: whether two products may share one; whether a hub checks it against the credential's registered client. | §5; registration §5.1, §18. |
| 8 | **State the owner boundary per credential in the shared contract**, so a one-listener hub can conform. *Decided, maintainer 2026-10-26:* yes (authority AU7), to be reviewed as the design matures. | §4. |
| 9 | **The data-source listing: data listener or owner's listener.** *Decided, maintainer 2026-10-26:* the owner's listener, with connector configuration: they change or describe the runtime and its resources, differently from an AID controller's registration. | Nocturne's `/api/v4/services` at `42275c812` (`Controllers/V4/Platform/ServicesController.cs`) mixes reads open to any signed-in credential (class `[Authorize]`, `:29`; the data-source list `:106`, connectors, uploader setup) with actions that require the owner atom `tenant.settings`: deleting a source's data (`:321-322`), deleting a connector's data (`:395-396`), a connector sync (`:438-439`) and a cursor reset (`:489-490`). Our listing of instances, bindings and overlaps is the owner's (authority §4). |
| 10 | **Operator actions on a tenant member's credentials.** *Decided, maintainer 2026-10-26:* hub-specific, outside the shared contract; cgm-remote-monitor's operator has none. | Nocturne's operator can list and remove a member's passkeys and OIDC identities and issue login and recovery codes (`TenantController.cs:186-310`); tenant-owner surface §F.1 lists create, list, suspend, activate, delete and export for the operator. |
| 11 | **Self-service tenant creation.** *Decided, maintainer 2026-10-26:* hub-specific; in cgm-remote-monitor creating a tenant stays the operator's. | Nocturne allows it behind `AllowSelfServiceCreation` (`PlatformController.cs:56-66`); §F.1 makes tenant creation the operator's. |
| 12 | **Typed record paths: start from Nocturne's v4 routes or define our own.** *Deferred, maintainer 2026-10-26,* until the identity decisions are settled; a detailed comparison of the two options, with criteria that can be benchmarked later, was asked for. | records §3 shares the model; the identity decisions (`ID-FORMAT-DECISION` and the others in the hub-implementer guide's backlog) decide how a typed write is matched and re-sent. Nocturne issue [#1932](https://github.com/nightscout/nocturne/issues/1932) (open) records that its v3 `POST` ignores a client's `identifier` and never upserts. |

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
