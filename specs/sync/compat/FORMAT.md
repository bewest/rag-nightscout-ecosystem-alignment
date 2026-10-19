# App compatibility data format

One file per group of apps (`ios.yaml`, `android.yaml`, `uploaders.yaml`, `readers.yaml`), read
by `tools/nsschema/compat_tables.py`, which writes the tables in
[spec/compatibility.md](../../../docs/30-design/platform/spec/compatibility.md), and checked by
`tools/nsschema/test_compat.py`. Each entry says what an app does today with a Nightscout hub,
layer by layer, and what it sees from a hub that implements the platform specifications **without
the app changing**. Every claim is read from source at the ref named, and cites the anchor it was
read from or the per-client file that holds it.

```yaml
- app: LoopFollow                     # the name people use
  kind: follower                      # controller | uploader | follower | reader | hub | tool
  ref: "LoopFollow@4a74b781 (v7.1.0)" # repo@sha, and the release when there is one
  source: reports/consumer-impact-15.0.9/clients/ios/LoopFollow.md   # the per-client file read
  layers:
    L0:                               # identity: ids it sends and reads, re-sends
      verdict: unchanged              # unchanged | gains | opt-in | affected | none
      today: "Writes no records; reads _id only from the subjects reply."
      newer: "Nothing it reads changes (I2, I4)."
      rules: [I2, I4]                 # rule ids or "<spec> §N" that decide the 'newer' cell
      anchors: ["LoopFollow@4a74b781 LoopFollow/Helpers/...swift:50-65"]   # optional
    L1: {...}                         # records: collections and fields it writes and reads
    L2: {...}                         # registration: what it declares (nothing today) and how a
                                      # newer hub attributes its writes (registration §17)
    L3: {...}                         # state, intent and commands: overrides, targets, profile
                                      # switches, remote commands, plans
    L4: {...}                         # sync: API v1, API v3, the socket, paging, count
    L5: {...}                         # authority: how it authenticates, which permissions it needs,
                                      # and what changes under TENANCY_MODE=multi
  notes: "optional, one or two sentences"
```

Verdicts, for the `newer` cell:

| verdict | means |
|---|---|
| `unchanged` | the app behaves as today; nothing it sends or reads changes |
| `gains` | the app benefits without changing (a fix, a better match, attribution) |
| `opt-in` | a capability exists for it, which it uses only if it changes (typed writes, registration, the command record, plans) |
| `affected` | something it does today answers differently; the cell says what and which rule |
| `none` | the app does not touch this layer |
