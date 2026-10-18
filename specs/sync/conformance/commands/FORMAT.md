# Command conformance case format

Cases for the [commands specification](../../../../docs/30-design/platform/spec/commands.md)
§2 and §4–§7, checked by `tools/nsschema/test_commands.py` against the reference in
`tools/nsschema/commands.py`. Every case is synthetic and its expectations are written by hand
from the specification, not from the reference.

Routing per registration §9 is given, not computed: each instance states the channels on which it
holds `device` command-sink, and over which interval.

```yaml
# Synthetic. SPEC-REG-COMMANDS; commands §N. Times are seconds; expectations authored by hand.
id: <file stem>
title: <one line>
rules: [CM13]
description: <what it shows>
control: <another case id>          # optional: the passing counterpart of a refusal
mode: single | multi
maxExpirySeconds: 3600
instances:
  i-ctl-a:
    tenant: A
    subject: s-ctl-a
    product: ControllerA
    definitionId: sha256:d-a          # an opaque string in cases
    simulated: false                   # optional; a simulated sink is never a destination
    sinks: {override: [0, null]}       # channel: [from, until), null = still holding
    proposes: [override]               # optional: channels it holds a granted propose role on
declares:                              # products declaring each channel, per tenant; none = no-command-destination
  A: {override: [ControllerA], example/slot: [ControllerA, ControllerB]}
shared: [override]                     # optional: shared channels, where §2's product inference does not apply
maxPayloadBytes: 4096                  # optional, default 4096: CM5
subjects:
  s-care: {tenant: A, permissions: [api:commands:create]}
  s-ctl-a: {tenant: A, permissions: []}
stateVersions:                         # optional: per tenant, product: [[from, version], ...]
  A: {ControllerA: [[0, v1], [50, v2]]}
calls:
  - {at: 10, kind: command, tenant: A, subject: s-care, channel: override,
     product: ControllerA,             # optional
     payload: {...}, expiresAt: 600,   # expiresAt optional (absolute seconds)
     requestId: r1}                    # optional
  - {at: 11, kind: push, bound: A, command: c1, via: socket}   # bound: null = no tenant bound
  - {at: 12, kind: fetch, tenant: A, subject: s-ctl-a, instance: i-ctl-a}
  - {at: 13, kind: enact, instance: i-ctl-a, command: c1,
     received: {...}}                  # optional: the payload as the controller received it
  - {at: 14, kind: report, tenant: A, subject: s-ctl-a, command: c1, state: succeeded,
     checked: {...},                   # optional: the payload whose hash the report names; default the command's
     reason: limit}                    # optional
  - {at: 15, kind: read, tenant: A, command: c1}
  - {at: 16, kind: restart, instance: i-ctl-a}                # the controller restarts (CM21)
  - {at: 20, kind: propose, tenant: A, subject: s-agent, instance: i-agent, channel: override,
     product: ControllerA,             # optional
     instanceId: i-ctl-a,              # optional: the instance the proposer read (CM13)
     payload: {...}, basedOn: v1, expiresAt: 600}
  - {at: 21, kind: approve, tenant: A, subject: s-care, proposal: p1,
     approves: {...}}                  # the payload whose hash the approval names
  - {at: 22, kind: reject, tenant: A, subject: s-care, proposal: p1}
  - {at: 23, kind: withdraw, tenant: A, subject: s-agent, proposal: p1}
  - {at: 24, kind: evaluate, tenant: A, subject: s-reader, proposal: p1, note: text}
end: 100                               # optional: the time final states are read at; default the last call's
expected:
  calls:                               # one entry per call, in order
    - {status: 201, commandId: c1, state: pending}                  # command accepted
    - {status: 409, code: no-command-destination, commandId: c2}    # refused at routing, recorded as not-routed
    - {status: 422, code: expiry-required}                          # refused, not recorded
    - {status: 200, commandId: c1, state: sent}                     # requestId re-send: the first command
    - {sent: true}                                                  # push
    - {sent: false, reason: withheld | expired | not-pending}
    - {status: 200, commands: [c1]}                                 # fetch
    - {state: succeeded} | {state: refused, reason: hash-mismatch}  # enact: the controller's check
    - {state: ignored, reason: duplicate}                           # enact: a commandId already decided (CM21)
    - {}                                                            # restart
    - {status: 200} | {status: 403, code: not-registration-owner}   # report
    - {status: 200, state: fetched} | {status: 404}                 # read
    - {status: 201, proposalId: p1}                                 # propose
    - {status: 201, commandId: c1, state: pending}                  # approve
    - {status: 200}                                                 # reject, withdraw
    - {status: 201}                                                 # evaluate
  commands: {c1: {state: succeeded, destination: i-ctl-a, proposalId: p1}}  # at `end`
                                       # plus hashMismatch: true when a report named another hash (CM7)
  proposals: {p1: {state: approved}}
```

Ids are assigned in order: commands `c1, c2, …` (accepted commands and commands refused at routing,
which CM1 records), proposals `p1, p2, …` (accepted proposals only). `destination` is `null` for a
command refused at routing. A permission or validation refusal is not recorded and gets no id.

Expiry: a command past `expiresAt` is never sent or fetched, and reads report it `expired` unless an
outcome came first. Push and fetch apply to `pending` or `sent` commands only.
