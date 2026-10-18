# L3 and L5 Commands: how a request or a proposal reaches a controller, and how its outcome comes back

*Contributor-facing. Living specification, current at `main` `9736bd65` (2026-10-18). Layers L3
and L5 of the [platform index](../README.md); terms are in the [glossary](glossary.md). Decisions:
[D18 and D19](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration)
and the maintainer's decisions of 2026-10-14 to 2026-10-18 recorded with them; the proposal
record was folded into this item on 2026-10-18. Queue: `SPEC-REG-COMMANDS`.*

*Specification 5 of 7 in the [reading order](../README.md#reading-order); after state and intent, whose acceptance policy (S10, S11) it builds on, and before sync-transport. Expect where a command goes, the command path today, rules CM1–CM20 for the command record, outcomes, proposals and delivery in each mode, compatibility with each controller, and the conformance cases.*

How a request to change therapy reaches a controller through a hub, what the hub records about it,
how the controller's outcome comes back, and the proposal and approval that can stand in front of
a command. The hub routes and records; it never decides whether a change is safe, never alters
what was asked, and never doses (D18). Validation and enactment stay the controller's.

Status: §2 is specified; §3 and §8 are evidenced; §4–§7 are proposed and specified with cases;
none is implemented.

## 1. Files

| file | what it is |
|---|---|
| [registration §9](registration.md#9-channels-roles-and-provenance) | channels and the `command-sink` role a destination holds |
| [authority §6](authority.md#6-who-may-receive-a-command) | which instance may hold a `device` command sink |
| [state and intent S10, S11](state-intent.md#2-rules) | what a controller declares it accepts from a hub, and by which paths commands reach it |
| [state and intent A12](state-intent.md#61-rules) | the state version a proposal can be based on |
| [agents in the ecosystem §4.3](../agent-trust-boundaries-2026-10-18.md#43-what-a-proposal-lifecycle-would-add--proposed-not-specified) | the proposal lifecycle this specification takes up |
| [intent landscape §6](../nightscout-intent-workflow-landscape-2026-10-09.md#6-the-remote-command-lifecycle) | command lifecycles per controller, read from source |
| `tools/nsschema/commands.py` | the reference decision function for §4–§7 |
| `specs/sync/conformance/commands/` | the cases it is checked against, with `tools/nsschema/test_commands.py` |

## 2. Where a command goes

A command names a channel ([registration §9](registration.md#9-channels-roles-and-provenance)).
It goes to the live `device` instance holding `command-sink` on that channel, on the command's
tenant. A command that names no product for a channel that is not shared goes to the one product
that declares that channel; when more than one product declares it, it is refused 409
`ambiguous-command-destination`, and naming the product resolves it. "Declares" reads
every product's current registration and stored definitions, in any state. With no holder, or a
channel no product declares, the command is refused 409 `no-command-destination`. The hub never
routes to a lapsed former holder, a `simulated` command sink, or the product's latest instance.
Which instance may hold the sink is [authority §6](authority.md#6-who-may-receive-a-command).

## 3. Commands today

Read from cgm-remote-monitor at the 15.0.8 release (`92d08342`), `dev` (`fade2299`) and the
multitenancy seam branch (`81a1f6ce`), 2026-10-18; "run" marks what was executed.

**One path carries a command.** `POST /api/v2/notifications/loop` (`lib/api2/notifications-v2.js`,
line 17 at 15.0.8, 21 on `dev`) hands a request to `lib/server/loop.js`, which sends an APNs push
to Loop.

| | what the hub does |
|---|---|
| permission | `notifications:loop:push`; of the default roles only `admin` holds it, so a caller needs `API_SECRET`, an admin token or a custom role (`lib/authorization/storage.js:232-238` on `dev`) |
| commands | four `eventType` values: `Temporary Override`, `Temporary Override Cancel`, `Remote Carbs Entry`, `Remote Bolus Entry`; anything else is refused "Unhandled event type" (`loop.js:67-110` on `dev`; run) |
| payload | the command's fields, `remote-address`, `notes`, `entered-by`, `sent-at`, `expiration` five minutes ahead, and `otp` only when the sender gave one (`loop.js:61-126`); no command id, nonce or signature, and no limit on an amount beyond "greater than zero" |
| the one-time password | forwarded, never checked; checking it is the controller's |
| destination | the device token and bundle id in the latest profile's `loopSettings` (`loop.js:31-47`); Trio publishes its token at the profile's top level, so this path does not reach Trio |
| credentials | the deployment's `LOOP_APNS_KEY`, `LOOP_APNS_KEY_ID` and `LOOP_DEVELOPER_TEAM_ID`, read only when `ENABLE` includes `loop`; without it, or with it but no `LOOP_*` variable set, `extendedSettings.loop` is never created and the route fails with a TypeError at `loop.js:16` (run without `ENABLE`, all three commits; read for the second case, `lib/server/env.js:281` on `dev`) |
| what is stored | nothing: neither file writes to a store, and the careportal's submit hook replaces its treatment write, so no treatment is stored either |
| response | 200 when APNs accepted the push (`loop.js:139-141` on `dev`); it says nothing about delivery, the password or enactment |
| outcome | none: no route, collection, socket event or field records that a controller received, accepted, refused or enacted a command |

Senders are the careportal's Loop plugin (`lib/plugins/loop.js:110-180` on `dev`) and the
NightscoutKit fork LoopCaregiver uses, for overrides, bolus and carbs when its newer
remote-command option is off; LoopCaregiver sends closed-loop and automatic-bolus changes to
`/api/v2/remotecommands` whatever the option, a route neither cgm-remote-monitor nor Nocturne
implements. Trio, LoopFollow and
AndroidAPS do not call this route.

**Everything else is data.** `Temporary Target`, `Profile Switch` and `Announcement` treatments are
stored and broadcast like any other record; a controller that downloads treatments may act on them
by its own rules, and the hub does not know whether it did. AndroidAPS `dev` writes signed command
envelopes and acknowledgements to the API v3 `settings` collection; the hub stores them as
documents and reads none of them. What each controller does with these paths is in [state and
intent §7](state-intent.md#7-commands-as-controllers-handle-them-today).

**Under `TENANCY_MODE=multi`, on the seam branch:**

- the request is bound to its tenant (`lib/server/tenant-middleware.js:263-272`), but nothing on the
  APNs path reads the binding: `ctx.loop` is built once per process (`lib/server/bootevent.js:229`),
  so the key, team id and device lookup are the deployment's, against one process-wide copy of the
  loaded data;
- multi requires PostgreSQL, and the PostgreSQL store at that commit implements only `entries`
  (`lib/storage/postgres-storage.js:127-133`), so no tenant's profile or treatments can be stored;
- socket emissions go to the bound tenant's room and are withheld when no tenant is bound
  (`lib/server/socket-tenancy.js:157-170,255-267`). The `dataUpdate` and alarm events come from the
  process-wide load cycle and are withheld; storage events from an API v3 request reach their
  tenant.

CM19 and CM20 are written against these two facts: a push from the load cycle reaches no one under
`multi`, and the only push credential today is the deployment's.

## 4. The command record (proposed)

| # | rule |
|---|---|
| CM1 | **The hub records a command before it sends it.** A command the hub accepts is stored as a record: `commandId` (assigned by the hub), its tenant, `channel`, the product named or inferred, the destination's `instanceId` and `definitionId` as routed, the `payload` exactly as received, `payloadHash` (`sha256:` over the payload's RFC 8785 canonical JSON, the rule [D19](registration.md#54-etag-and-idempotency) uses for definition ids), the `initiator` in the form [state and intent S8](state-intent.md#2-rules) gives it, the subject that sent it, `proposalId` and the proposal's `basedOn` when it came from an approval (§6), `createdAt`, `expiresAt` and `state`. A command refused at routing (§2) is recorded as `not-routed`, with its reason, and never sent. |
| CM2 | **Routed once.** The destination is fixed when the command is accepted; it is never re-routed to a later holder, which would enact a request its sender addressed to another device. If the destination lapses or loses its role while the command is `pending`, nothing was handed over and the command becomes `undeliverable`. If that happens after it was `sent`, the controller may have it, and the command becomes `unconfirmed`. |
| CM3 | **An expiry is required.** A command without `expiresAt`, or with one not after the request's time, is refused 422 `expiry-required`; one more than the hub's `commands.maxExpirySeconds` after the request is refused 422 `expiry-too-long`. Times are the hub's. A command at or past its expiry is never sent or fetched. At its expiry a `pending` command becomes `expired`, because nothing was handed over; a `sent` or `fetched` command becomes `unconfirmed`, because the controller may have enacted it; an acknowledged command keeps the controller's state. A hub never reports a command that may have been enacted as `expired` or `undeliverable`, which a sender would read as safe to send again. |
| CM4 | **Re-sending a request.** A sender may give a `requestId`. Within a tenant and subject, a second command with the same `requestId`, `channel`, product as the request names it (naming none differs from naming the one that would be inferred) and `payloadHash` returns the first command and its current state; with any of them different it is refused 409 `request-id-reused`. Without a `requestId`, every request is a new command. |
| CM5 | **The hub does not judge.** The hub checks only that the channel accepts commands, the routing, the expiry, the size (a payload over the hub's `commands.maxPayloadBytes` of canonical JSON is refused 413 `payload-too-large`) and the sender's permission (403 `not-authorised` without `api:commands:create`). It never checks a dose, a limit or the therapy state, and it never changes the payload. |
| CM6 | **Tenant isolation.** A command's tenant is the tenant its request resolved to. Routing, sending, fetching, proposals, reports and reads see only that tenant: a command, proposal or instance from another tenant is 404, as one that does not exist is, so a request never reveals that it exists. |

**Order of checks.** Where more than one refusal applies, the first wins: another tenant (404), then the sender's permission and ownership (403), then the request's own content (413, 422), then state (409). Among an approval's 409s the order is: the proposal's state (`proposal-expired`, `proposal-closed`), `hash-mismatch`, routing, `destination-changed`, `state-changed`. A push checks the binding (`withheld`) before the command's state, and applies only to a `pending` or `sent` command (`not-pending` otherwise).

**States.** The hub sets `pending`, `not-routed`, `sent`, `fetched`, `unconfirmed`, `undeliverable` and `expired`; only the
destination sets `acknowledged`, `succeeded`, `failed` and `refused` (§5).

| state | set by | means |
|---|---|---|
| `pending` | hub | accepted and routed; nothing sent yet |
| `not-routed` | hub | refused at routing (§2); its reason is recorded |
| `sent` | hub | handed to a push transport (§7); not a receipt |
| `fetched` | hub | the destination instance read it with its own credential (§7); a receipt, not an outcome |
| `unconfirmed` | hub | handed over, with no outcome: `sent`, then its expiry passed or its destination lost the role; or `fetched`, then its expiry passed. It may have been enacted (CM2, CM3) |
| `undeliverable` | hub | the destination lapsed or lost its role before anything was handed over (CM2) |
| `expired` | hub | its expiry passed before anything was handed over (CM3) |
| `acknowledged` | controller | received; validating or enacting |
| `succeeded` | controller | enacted |
| `failed` | controller | accepted but not enacted, such as a pump that did not respond |
| `refused` | controller | declined by the controller's own checks |

`succeeded`, `failed`, `refused`, `not-routed`, `undeliverable` and `expired` are final; the hub sets the last
three only for a command that was never handed over. `sent`, `fetched` and `unconfirmed` are never
reported as success or as failure.

## 5. Outcomes (proposed)

| # | rule |
|---|---|
| CM7 | **Only the destination reports.** An outcome report names the `commandId` and is accepted only from the bound subject of the destination the command was routed to, whether or not that instance still holds the role; any other subject is refused 403 `not-registration-owner`. The report carries `state` (`acknowledged`, `succeeded`, `failed` or `refused`; any other is 422 `invalid-state`), the `payloadHash` the controller computed over the payload it received, a `reason` when refused or failed, and, when enacted, the identity of the record that shows the effect ([identity](identity.md)). A reported hash that differs from the command's is recorded as reported, with the record marked as a mismatch; the hub does not refuse it, because the report is evidence of what the controller did. |
| CM8 | **Reasons.** A refusal or failure reason is one of `hash-mismatch`, `expired`, `not-accepted` (the controller's acceptance preference is off, [S10](state-intent.md#2-rules)), `limit` (a limit the controller enforces) or `{value: other, controllerTerm}`; a bare unknown string is refused 422 `invalid-reason`. The hub records the reason and does not interpret it. |
| CM9 | **One outcome.** After a final state, a further report is refused 409 `already-final`. A report on an `unconfirmed` command is accepted and replaces it: that state is the hub's inference, and the controller's report of what it did is better evidence. `acknowledged` may precede a final state and may be skipped. |
| CM10 | **The controller checks the hash.** Before enacting, the controller recomputes `payloadHash` over the payload it received and refuses `hash-mismatch` when it differs from the hash the command carries. It also refuses a command past `expiresAt` by its own clock. These checks are the controller's, as all validation is (D18). The controller receives the payload and the hash from the same hub, so the check detects a payload changed in transit or storage; it does not show that a hub, or anything acting as one, delivered what an approver approved, and it does not authenticate the sender. Binding an approval to a payload end to end needs a signature by the sender or approver. Authentication between sender and controller, such as Loop's one-time password, Trio's shared secret or AndroidAPS's per-client signature (§8), stays the controller's, and the hub carries it unread. |

## 6. Proposals and approvals (proposed)

```
propose → (evaluate) → approve | reject | withdraw | expire → command (§4) → outcome (§5)
```

| # | rule |
|---|---|
| CM11 | **A proposal.** A proposal names the proposing instance, the target `channel` and, when known, the target product and `instanceId`; the `payload` and its `payloadHash`, under CM5's size limit; `basedOn`, the [state version](state-intent.md#61-rules) of the target product that the proposer read, required (422 `based-on-required`); and `expiresAt`, under the same limits as CM3. The hub routes the proposal when it is made (§2) and records the destination with its `definitionId`: a proposal with no destination is refused as a command would be, with nothing recorded; a named `instanceId` on another tenant, or none at all, is 404 (CM6); and one that is not the destination is refused 409 `destination-changed`. Its states are `open`, `approved`, `rejected`, `withdrawn` and `expired`; only `open` changes. A proposal is read by its tenant's subjects holding `api:proposals:read` or `api:commands:create`. |
| CM12 | **Who may propose.** The sender holds `api:proposals:create`, and the proposing instance is its own and holds a granted propose role on the channel: an `other` role that the hub's capability document lists as proposing ([registration §9](registration.md#9-channels-roles-and-provenance)); a hub grants only roles it lists. Without the permission it is 403 `not-authorised`; an instance that is not the sender's is 403 `not-registration-owner`; without the role it is 403 `role-not-granted`. Reading confers neither: a `readable` credential, or a tool holding one, cannot propose. |
| CM13 | **An approval binds to one payload.** An approval names the `proposalId` and the `payloadHash` it approves. A hash that differs from the proposal's is refused 409 `hash-mismatch`; a proposal past its expiry is refused 409 `proposal-expired`; one that is not `open` is refused 409 `proposal-closed`. The approval routes again: with no destination it is refused as a command would be (§2), and when the destination differs from the one recorded at the proposal it is refused 409 `destination-changed`, because the proposer read one device's state and the change would reach another. A refused approval leaves the proposal `open` and creates no command. An accepted approval creates one command (CM1) whose payload is the proposal's, byte for byte, with the same hash, `proposalId` and `basedOn` set, and the proposal's `expiresAt`. |
| CM14 | **Who may approve.** The approver holds the permission to send the command itself (`api:commands:create`), else 403 `not-authorised`; approving is sending. The subject that proposed cannot approve its own proposal (403 `self-approval`). Rejecting needs the same permission; withdrawing is the proposer's alone; either by anyone else is 403 `not-authorised`. |
| CM15 | **Based on.** An approval is refused 409 `state-changed` when the target product's state version at the hub, at the time of approval, differs from the proposal's `basedOn`. This checks the hub's record of what the controller reported, the way an etag does; it does not tell the approver that the controller's own state is unchanged, which only the controller's own validation can (D18); the controller is given `basedOn` but cannot recompute it, because it versions the hub's record. |
| CM16 | **Evaluations are evidence.** Anyone who may read the proposal (CM11) may attach an evaluation: a risk check, a second model's opinion, a request for review. An evaluation never changes the proposal's state and never approves. |

## 7. Delivery in each mode (proposed)

| # | rule |
|---|---|
| CM17 | **The record is the command.** A push transport may carry the payload and its hash, but the hub's record (CM1) is what states, outcomes and audit refer to. |
| CM18 | **Fetch.** The destination reads its `pending` and `sent` commands with its own credential. This works the same in both modes, because the request is bound to the tenant; it is the path a hub must offer. A fetch returns only commands whose destination is that instance; a fetch naming an instance that is not the credential's own is 403 `not-registration-owner`, and an instance that no longer holds the role gets an empty list. |
| CM19 | **Push only inside a bound request.** A push (a socket event to the destination, or a platform push such as APNs) is sent only inside a request already bound to the command's tenant, such as the request that accepted the command or approval, or a later request from the destination. Under `TENANCY_MODE=multi`, nothing is sent from a context with no tenant bound, such as the load cycle; an emission there, or one bound to another tenant, is withheld and the command stays `pending` until it is fetched. Under `single` the one tenant is always bound. |
| CM20 | **Credentials for a platform push are the tenant's.** A platform push uses credentials held by the command's tenant, never the deployment's. |

What a mode changes beyond these, such as the storage key and the credential kinds a command
record names, is the registration contract per mode (`SPEC-REG-MODES`, not written).

## 8. Compatibility

Read from Loop (`c30b5c89`, NightscoutService `2cef489`), Trio (`0b29cd534`), AndroidAPS
(`7e1d537d49`, `dev`), LoopCaregiver (`2305718`) and LoopFollow (`4a74b781`), 2026-10-18; nothing
was run.

| path | hub in the path | sender authentication | freshness | correlation | outcome today | against §4–§7 |
|---|---|---|---|---|---|---|
| careportal or LoopCaregiver → hub → Loop (APNs) | yes | one-time password for bolus and carbs, single use and kept by Loop; none for overrides | `expiration`, checked when present; the hub adds five minutes | none; Loop's de-duplication on `sent-at` is in memory and lost on restart | a `Note` with free text on failure; on success the resulting record (an override carries its remote trigger) and, to a direct sender that included encrypted return details, a reply push | outside §4–§7: Loop registers no instance and holds no command sink, and these senders give no expiry, so the route has no record, no routing and a hub-set expiry. A hub keeps it as it is or retires it; bringing it under these rules needs Loop to register |
| LoopCaregiver "Remote Commands 2" (experimental, off by default; closed-loop and automatic-bolus changes always) | expects `/api/v2/remotecommands`, which neither cgm-remote-monitor nor Nocturne implements | one-time password | none on the record | the record's `_id` | `Pending` → `InProgress` → `Success` or `Error` | the closest to CM1 and CM7: its states map to `pending`, `acknowledged`, `succeeded`, and `failed` or `refused`; who may change a status is not stated, and no Loop build in the checkouts reads it |
| LoopFollow → Loop or Trio (direct APNs) | no; the device token is read from the hub's profile | as above; Trio encrypts the whole payload with a shared secret | Loop: as above; Trio: ±600 s around the sender's time, fixed, no expiry field | none | a reply push to the sender; a `Note` on failure | outside the hub; a hub sees only the resulting records |
| AndroidAPS client control (`dev`, not released) | the `settings` collection carries it; the hub reads none of it | HMAC per paired client, a strictly increasing counter | ±5 min and `validUntil` (unbounded by default; its senders set 8 s, 60 s or 5 min) | the counter | signed `Executing`, `Done` (`Ok`, `Failed`, `Expired`), and a late `Delivery` `Failed` | the only path whose outcome names its command; its doses are two-step, computed and capped on the controller between prepare and commit |
| AndroidAPS SMS | no | allowed number, one-time password and PIN | 5 min to confirm | the message thread | an SMS reply | outside the hub |

What in this table bears on the rules:

- **A late failure after success.** AndroidAPS reports `Done` `Ok` when the pump queue accepts a
  bolus and `Delivery` `Failed` if the pump later fails it; Trio replies "initiating bolus" before
  it enacts and may reply failed after. CM9 as written refuses a report after `succeeded` (§9).
- **One command, part enacted.** Trio's meal command stores the carbs before it validates the
  bolus, so a refused bolus leaves carbs entered and the reply says failed. A single final state
  cannot say which part happened (§9).
- **No controller computes a payload hash** (CM10); each checks its own authentication instead.
- **Expiry is not uniform.** Loop checks an `expiration` only when one is sent; Trio checks a
  fixed window around the sender's time; AndroidAPS's `validUntil` is unbounded unless the sender
  sets it; Remote Commands 2 records carry none. CM3 requires one of every command.
- **Sender authentication is end to end.** Every controller that accepts a remote dose
  authenticates the sender itself; a hub forwards that material and is not trusted with it.

## 9. Open

1. **Choices for the maintainer:**
   - **How a capability document marks a listed `other` role as proposing** (CM12). Today it
     lists role names only; nothing says which listed role may propose.
   - **The command's expiry after an approval** (CM13 proposes the proposal's `expiresAt`), or a
     new one set at approval within the proposal's.
   - **Refusing a stale approval** (CM15), or only showing the approver that the state version
     changed.
   - **Recording refusals at routing** (CM1) as `not-routed` commands, or answering them only.
   - **Who may approve** (CM14): today anyone who may send the command; a grant could narrow it
     ([authority §7](authority.md#7-delegation-not-decided)).
2. **A controller check before approval.** The proposal lifecycle drew `propose → validate →
   (evaluate) → approve`; CM11–CM16 send nothing to the controller before approval, because no
   controller offers a dry run of a remote command except AndroidAPS `dev`'s two-step prepare and
   commit, which computes and caps a dose on the controller before it is committed.
3. **The payload grammar.** No definition declares the shape of a command's payload; the hub
   stores it unread, and an approver's display has nothing to render its units or product from
   (UCA-PROP-004).
4. **Outcomes that change after a final state:** a late delivery failure after success (§8), and
   a command enacted in part (§8). Either a further state (`failed` after `succeeded`, with the
   record keeping both) or an outcome per part (UCA-CMD-011, UCA-CMD-013).
5. **The grant** that lets a person approve for someone else, and auto-approval: [authority
   §7](authority.md#7-delegation-not-decided).
6. **The registration contract per tenancy mode** (`SPEC-REG-MODES`).
7. **Found by the [control-loop analysis](control-loops.md):**
   - **Enacting a command once** (UCA-CMD-006). Delivery is at least once: a push may carry a
     command that a fetch returns again (CM18). No rule requires a controller to enact one
     `commandId` at most once, or to keep that record across a restart.
   - **Outstanding commands on a channel** (UCA-CMD-001, UCA-PROP-007). A sender or approver is
     not shown the channel's commands that are not final, and the state version changes only when
     the controller's records arrive (A12), so two approvals in that window both pass CM15. The
     choices: show them with each send and approval; refuse a second approval on a channel while
     a command from an approval is not final; or include them in what CM15 compares.
   - **The definition at approval** (UCA-PROP-008). CM11 records the destination's
     `definitionId`; CM13 refuses `destination-changed` only when the instance differs, so an
     instance that renewed under a new definition receives a payload approved under the old one.
   - **Proposal volume** (UCA-PROP-002). Nothing limits the open proposals one instance holds on
     a channel.
   - **Doses since `basedOn`** (UCA-PROP-012). The state version covers active intents (A12), not
     doses or carbs, so a dose proposal passes CM15 after the person has dosed locally.
   - **A process holding the destination's credential** (UCA-CMD-014). CM7 and CM18 check the
     subject, not the process: under `single` every holder of `API_SECRET` is one subject, so
     another app can fetch a command, which moves it to `fetched` and out of the controller's
     next fetch, or report its outcome.
   - **Cancelling a command** (UCA-CMD-015). A sender cannot cancel a `pending` command whose
     reason went away. Cancelling before hand-over is safe; after it, a cancel can only ask.
   - **Approving at once** (UCA-PROP-013). CM13 lets only an `open` proposal change, and
     `approve-approved-proposal` shows a second approval refused; that the change from `open` to
     `approved` is atomic under concurrent approvals is not stated.
   - **The operator's limits** (UCA-AUTH-006). `commands.maxExpirySeconds` bounds every expiry
     (CM3) and has no bound of its own.

## 10. Conformance cases

The routing cases are part of the registration suite (`tools/nsschema/test_registration_instances.py`);
the rest are checked by `tools/nsschema/test_commands.py` against `tools/nsschema/commands.py`,
which also checks on every case that nothing reaches another tenant, nothing is sent or fetched
at or after its expiry, nothing is pushed unbound under `multi`, and an approved command carries
the payload hash its approval named (the case's `received` payload stands for what was delivered). CM20 has no case; CM17 has one, `sent-and-fetched-are-not-success`.

115 cases.

<!-- BEGIN GENERATED: commands-cases (tools/nsschema/spec_cases.py) -->
| case | shows | expected | control |
|---|---|---|---|
| `instances/command-routed` | A command for a channel goes to its command-sink holder | 200 routed |  |
| `instances/command-unknown-slot` | A command for a slot no product declares has no destination | 409 rejected; no-command-destination | `command-inferred-one-product` |
| `instances/command-ambiguous-destination` | A command naming no product for a slot two products declare is refused as ambiguous | 409 rejected; ambiguous-command-destination | `command-named-product` |
| `instances/command-inferred-one-product` | A command naming no product goes to the one product that declares its slot | 200 routed |  |
| `instances/command-named-product` | Naming the product resolves a command for a slot two products declare | 200 routed |  |
| `commands/acknowledged-stays-past-expiry` | An acknowledged command with no further report stays acknowledged past expiry | rules CM3 |  |
| `commands/acknowledged-survives-expiry` | A command acknowledged before its expiry is not reported expired | rules CM3, CM9 |  |
| `commands/acknowledged-then-succeeded` | acknowledged may precede a final state | rules CM9 |  |
| `commands/approve-after-proposal-expiry` | An approval after the proposal's expiry is refused | rules CM13 | `approve-creates-command-with-proposal-payload` |
| `commands/approve-after-sink-passed-unnamed` | An approval after the sink passed to another instance is refused, even with no instanceId named | rules CM13 | `approve-before-sink-passes` |
| `commands/approve-approved-proposal` | An approved proposal cannot be approved again | rules CM13, CM14 | `approve-creates-command-with-proposal-payload` |
| `commands/approve-before-sink-lapses` | An approval while the recorded destination still holds the sink is accepted | rules CM13 |  |
| `commands/approve-before-sink-passes` | An approval before the sink passes routes to the instance recorded at proposal | rules CM13 |  |
| `commands/approve-by-other-subject` | A subject other than the proposer approves | rules CM14 |  |
| `commands/approve-creates-command-with-proposal-payload` | An approval creates one command carrying the proposal's payload | rules CM13, CM14, CM1 |  |
| `commands/approve-destination-changed` | An approval is refused when the named instance no longer holds the sink | rules CM13 | `approve-named-instance-still-holder` |
| `commands/approve-hash-mismatch` | An approval naming a different payload's hash is refused | rules CM13 | `approve-creates-command-with-proposal-payload` |
| `commands/approve-named-instance-still-holder` | An approval routes to the instance the proposal named while it holds the sink | rules CM13 |  |
| `commands/approve-no-holder` | An approval when no instance holds the sink any more is refused at routing | rules CM13, CM1 | `approve-before-sink-lapses` |
| `commands/approve-rejected-proposal` | A rejected proposal cannot be approved | rules CM13, CM14 | `approve-creates-command-with-proposal-payload` |
| `commands/approve-state-changed-named-product` | basedOn is checked against the product the proposal names | rules CM15, CM11 | `approve-state-unchanged-named-product` |
| `commands/approve-state-changed` | An approval after the target's state version moved is refused | rules CM15 | `approve-state-unchanged` |
| `commands/approve-state-unchanged-named-product` | An approval for a named product whose state version is unchanged is accepted | rules CM15, CM11, CM13 |  |
| `commands/approve-state-unchanged` | An approval while the target's state version equals basedOn is accepted | rules CM15 |  |
| `commands/approve-withdrawn-proposal` | A withdrawn proposal cannot be approved | rules CM13, CM14 | `approve-creates-command-with-proposal-payload` |
| `commands/approve-without-command-permission` | Approving needs the permission to send the command | rules CM14 | `approve-creates-command-with-proposal-payload` |
| `commands/approved-command-has-proposal-expiry` | The command an approval creates expires when the proposal would have | rules CM13, CM3 |  |
| `commands/command-without-permission` | A sender without api:commands:create is refused and not recorded | rules CM5 | `route-to-holder` |
| `commands/enact-after-expiry-refused` | The controller refuses a command past expiresAt by its own clock | rules CM10 | `enact-identical-payload-succeeds` |
| `commands/enact-hash-mismatch-refused` | The controller refuses a received payload whose hash differs | rules CM10, CM7, CM8 | `enact-identical-payload-succeeds` |
| `commands/enact-identical-payload-succeeds` | The controller enacts a payload whose hash matches | rules CM10 |  |
| `commands/evaluate-by-command-sender` | A subject holding api:commands:create may read and so evaluate | rules CM16, CM11 |  |
| `commands/evaluate-without-read` | A subject that may not read the proposal cannot evaluate it | rules CM16, CM11 | `evaluation-does-not-change-proposal` |
| `commands/evaluation-does-not-change-proposal` | An evaluation is evidence and never changes the proposal | rules CM16 |  |
| `commands/expiry-at-maximum` | An expiry exactly at the maximum is accepted | rules CM3 |  |
| `commands/expiry-at-request-time` | An expiry equal to the request's time is refused | rules CM3 | `expiry-one-second-after-request` |
| `commands/expiry-one-second-after-request` | An expiry one second after the request is accepted | rules CM3 |  |
| `commands/expiry-required` | A command without expiresAt is refused and not recorded | rules CM3 | `route-to-holder` |
| `commands/expiry-too-long` | An expiry beyond commands.maxExpirySeconds is refused | rules CM3 | `expiry-at-maximum` |
| `commands/fetch-after-expiry-is-empty` | A command past its expiry is neither fetched nor pushed, and reads report expired | rules CM3 | `fetch-before-expiry` |
| `commands/fetch-after-role-lost-is-empty` | An instance that no longer holds the role fetches an empty list | rules CM18, CM2 | `fetch-before-role-lost` |
| `commands/fetch-before-expiry` | A command fetched before its expiry is delivered | rules CM3 |  |
| `commands/fetch-before-role-lost` | The same instance fetches while it holds the role | rules CM18, CM2 |  |
| `commands/fetch-instance-other-tenant-404` | A fetch naming an instance on another tenant is 404 | rules CM6, CM18 | `fetch-instance-own-tenant` |
| `commands/fetch-instance-own-tenant` | The destination fetches on its own tenant | rules CM6, CM18 |  |
| `commands/fetch-naming-another-instance` | A fetch naming an instance that is not the credential's own is refused | rules CM18 | `fetch-returns-own-commands` |
| `commands/fetch-returns-own-commands` | A fetch returns only the fetching instance's own commands | rules CM18 |  |
| `commands/fetched-before-holder-changes` | A command fetched before the holder changes stays fetched | rules CM2 |  |
| `commands/fetched-then-expiry-unconfirmed` | A fetched command with no outcome becomes unconfirmed at its expiry | rules CM3 |  |
| `commands/hub-does-not-judge-payload` | The hub neither checks nor alters the payload | rules CM5, CM10 |  |
| `commands/no-request-id-two-commands` | Without a requestId, identical requests are two commands | rules CM4 |  |
| `commands/outcome-before-expiry-stays` | An outcome reported before expiry is still the state after it | rules CM3, CM9 |  |
| `commands/payload-too-large` | A payload over maxPayloadBytes is refused and not recorded | rules CM5 | `payload-within-limit` |
| `commands/payload-within-limit` | A payload under maxPayloadBytes is accepted | rules CM5 |  |
| `commands/pending-expires-report-refused` | A pending command expires, and a report after expired is refused | rules CM3, CM9 | `report-on-unconfirmed-after-expiry-accepted` |
| `commands/proposal-expiry-required` | A proposal without expiresAt is refused | rules CM11, CM3 | `propose-with-permission-and-role` |
| `commands/proposal-expiry-too-long` | A proposal's expiry is under the command limits | rules CM11, CM3 | `propose-with-permission-and-role` |
| `commands/propose-by-instance-owner` | The instance's own subject proposes | rules CM12 |  |
| `commands/propose-instance-other-tenant-404` | A proposal naming a proposing instance on another tenant is 404 | rules CM6, CM12 | `propose-instance-own-tenant` |
| `commands/propose-instance-own-tenant` | The proposing instance's own subject proposes on its own tenant | rules CM6, CM12 |  |
| `commands/propose-named-instance-is-destination` | A proposal naming the destination is accepted | rules CM11 |  |
| `commands/propose-named-instance-not-destination` | A proposal naming an instance that is not the destination is refused | rules CM11 | `propose-named-instance-is-destination` |
| `commands/propose-named-instance-other-tenant-404` | A proposal naming a target instance on another tenant is 404 | rules CM6, CM11 | `propose-named-instance-is-destination` |
| `commands/propose-no-holder` | A proposal on a channel no instance holds is refused as a command would be | rules CM11, CM1 | `propose-with-permission-and-role` |
| `commands/propose-payload-too-large` | A proposal whose payload is over maxPayloadBytes is refused | rules CM11, CM5 | `propose-payload-within-limit` |
| `commands/propose-payload-within-limit` | A proposal whose payload is under maxPayloadBytes is accepted | rules CM11, CM5 |  |
| `commands/propose-with-another-subjects-instance` | A sender cannot propose as an instance that is not its own | rules CM12 | `propose-by-instance-owner` |
| `commands/propose-with-permission-and-role` | A sender with the permission and the propose role proposes | rules CM11, CM12 |  |
| `commands/propose-without-based-on` | A proposal without basedOn is refused | rules CM11 | `propose-with-permission-and-role` |
| `commands/propose-without-permission` | A credential that can only read cannot propose | rules CM12 | `propose-with-permission-and-role` |
| `commands/propose-without-role` | The permission without a propose role on the channel is refused | rules CM12 | `propose-with-permission-and-role` |
| `commands/push-bound-other-tenant-withheld` | Under multi, a push bound to another tenant is withheld | rules CM19, CM6 | `push-bound-own-tenant-under-multi` |
| `commands/push-bound-own-tenant-under-multi` | Under multi, a push bound to the command's own tenant is sent | rules CM19 |  |
| `commands/push-bound-sent-under-multi` | Under multi, a push inside a request bound to the command's tenant is sent | rules CM19 | `push-unbound-withheld-under-multi` |
| `commands/push-unbound-sent-under-single` | Under single, the one tenant is always bound and the push is sent | rules CM19, CM18 |  |
| `commands/push-unbound-withheld-under-multi` | Under multi, a push with no tenant bound is withheld and fetch delivers | rules CM19, CM18 | `push-unbound-sent-under-single` |
| `commands/pushed-then-lapse-unconfirmed` | A command handed to a push and then losing its destination is unconfirmed, and a report replaces it | rules CM2, CM9 |  |
| `commands/read-other-tenant-404` | A command id read from another tenant is 404 | rules CM6 | `read-own-tenant` |
| `commands/read-own-tenant` | A command id read on its own tenant is found | rules CM6 |  |
| `commands/reject-proposal` | A subject that may send the command rejects a proposal | rules CM14 |  |
| `commands/reject-without-command-permission` | Rejecting needs api:commands:create | rules CM14 | `reject-proposal` |
| `commands/report-after-final-refused` | A second outcome after a final state is refused | rules CM9 | `acknowledged-then-succeeded` |
| `commands/report-after-undeliverable-refused` | A report after undeliverable is refused: the state is final | rules CM2, CM9 | `pushed-then-lapse-unconfirmed` |
| `commands/report-from-destination-accepted` | The destination's bound subject reports an outcome | rules CM7 |  |
| `commands/report-from-other-subject-refused` | Another subject cannot report, even one that may send commands | rules CM7 | `report-from-destination-accepted` |
| `commands/report-on-unconfirmed-after-expiry-accepted` | A report on a command unconfirmed at expiry is accepted and replaces it | rules CM3, CM9 |  |
| `commands/report-other-tenant-404` | A report for another tenant's command id is 404 | rules CM6, CM7 | `report-from-destination-accepted` |
| `commands/report-reason-bare-string-invalid` | A bare unknown reason string is invalid | rules CM8 | `report-reason-other-accepted` |
| `commands/report-reason-other-accepted` | A controller-specific reason is given as other with its own term | rules CM8 |  |
| `commands/report-state-fetched-invalid` | A report with state fetched is refused | rules CM7 | `report-from-destination-accepted` |
| `commands/report-state-sent-invalid` | A report with state sent is refused | rules CM7 | `report-from-destination-accepted` |
| `commands/request-id-different-payload-refused` | The same requestId with a different payload is refused | rules CM4 | `request-id-same-payload-returns-first` |
| `commands/request-id-other-channel-refused` | The same requestId and payload on another channel is refused | rules CM4 | `request-id-same-channel-returns-first` |
| `commands/request-id-other-product-refused` | The same requestId and payload naming another product is refused | rules CM4 | `request-id-same-product-returns-first` |
| `commands/request-id-reordered-keys-same-hash` | Key order does not change the payload hash a re-send is matched on | rules CM1, CM4 |  |
| `commands/request-id-same-channel-returns-first` | The same requestId, channel, product and payload returns the first command | rules CM4 |  |
| `commands/request-id-same-payload-returns-first` | Re-sending the same requestId and payload returns the first command | rules CM4 |  |
| `commands/request-id-same-product-returns-first` | The same requestId naming the same product returns the first command | rules CM4 |  |
| `commands/request-id-scoped-to-subject` | A requestId is matched within one subject | rules CM4 |  |
| `commands/route-ambiguous-declared-channel` | An unshared channel declared by two products needs a product | rules CM1 | `route-ambiguous-resolved-by-product` |
| `commands/route-ambiguous-resolved-by-product` | Naming the product resolves an ambiguous channel | rules CM1 |  |
| `commands/route-inferred-from-declaring-product` | A command naming no product goes to the one product declaring the channel | rules CM1 |  |
| `commands/route-lapsed-holder-not-destination` | A lapsed former holder is never a destination | rules CM1 | `route-to-holder` |
| `commands/route-latest-instance-not-destination` | The product's latest instance is not a destination unless it holds the sink | rules CM1 | `route-to-holder` |
| `commands/route-no-holder` | No instance holds command-sink: refused and recorded as not-routed | rules CM1 | `route-to-holder` |
| `commands/route-other-tenant-holder-not-used` | A holder on another tenant is never the destination | rules CM1, CM6 | `route-own-tenant-holder` |
| `commands/route-own-tenant-holder` | The same command on the holder's own tenant is routed | rules CM1, CM6 |  |
| `commands/route-simulated-sink-not-destination` | A simulated command sink is never a destination | rules CM1 | `route-to-holder` |
| `commands/route-to-holder` | A command naming the product goes to the instance holding command-sink | rules CM1 |  |
| `commands/route-undeclared-channel` | A channel no product declares has no destination | rules CM1 | `route-inferred-from-declaring-product` |
| `commands/self-approval-refused` | The proposer cannot approve its own proposal | rules CM14 | `approve-by-other-subject` |
| `commands/sent-and-fetched-are-not-success` | A push and a fetch are receipts, not outcomes | rules CM9, CM17 |  |
| `commands/undeliverable-not-rerouted` | A destination that stops holding before fetching makes the command undeliverable | rules CM2 | `fetched-before-holder-changes` |
| `commands/withdraw-by-other-subject` | Only the proposer may withdraw | rules CM14 | `withdraw-by-proposer` |
| `commands/withdraw-by-proposer` | The proposer withdraws its proposal | rules CM14 |  |
<!-- END GENERATED: commands-cases -->
