# Explicit unaccepted measurement admission — source proof

Focused source capability PASS at
`7219ad70bd3b284d23573a3bfb115883136fd97a`, based on frozen alignment
`5d7fa02746f4695a222f1fc400dc59b61a8c717e`. This permits separately authorized
pre-acceptance collection, not acceptance or a runtime measurement. No Docker,
application, cloud or capacity execution occurred in this lane.

The existing remote-pilot workload, profile, counts, cadence, image/ownership,
quiet-host, stored-write oracle, clinical/recovery, cleanup and failed-level stop
predicates remain. The fresh-image diagnostic's <=10 bound stays intact.
Default accepted admission remains supported. The exact new authorization,
explicit CLI and output scope are documented in the source
[contract](../../../tools/mt-bench/m7-joined/UNACCEPTED-MEASUREMENT.md).
[The separate support descriptor](measurement-capabilities.json) leaves cap4
unchanged. Its pair/instrument/image/run/role/count/180-minute/diagnostics fields
must agree; unknown acceptance claims refuse.

Cell/aggregate records explicitly remain functionalAcceptance UNACCEPTED and
capacityAcceptance NOT_GRANTED. Collection completion is separate from unchanged
correctness verdict. Failures retain raw data and never advance levels or rewrite
the original summary. Accepted source validators and the actual receipt gate
reject unaccepted scope, even when otherwise valid cells are wrapped.
A later acceptance review must keep these captured originals unchanged.

[Instrument](instrument.json): SHA256
`63844506159ee61f2335d8e94694a21cc48bc558b36f8146d8eb968ebdfa4f6d`,40 files.
Receipt gate, outside that instrument: SHA256
`316a3747e86dd519c8ce302055873903e564862a590cd8e38c4d5bea3b6e7b86`,35,213 bytes.
Source and transport/native proof must use the newly reviewed tuple; previous
TIME/receipt hashes are not silently relabelled.

## Actual focused checks

- New source admission/output/topology/campaign recording controls:9PASS.
- Existing contract module:19PASS, including original accepted and diagnostic paths.
- Existing actual receipt module:51PASS on final bytes, including accepted positives.
- Omit only new receipt image equality in memory: RED, `RuntimeError not raised`.
- Omit only actual cell-gate scope refusal in memory: RED, `ValueError not raised`.
  Its baseline otherwise-valid accepted fixture first passes; the red is not a
  setup failure. Restored source9PASS. No source files changed by controls.

The initial existing receipt run had one failure: the copied standalone-validator
ablation could not import a newly eager capacity dependency. It was not counted
green. The repair keeps the metadata refusal self-contained in the gate; the
existing targeted ablation then passes and the final whole module51passes.
Initial and restored outputs retain that attribution. No application predicate
or source schema was loosened to repair the check.

Commands are ordinary unittest discovery with patterns `test_unaccepted.py`,
`test_contract.py`, and `test_m7_joined_receipt.py`; controls are the explicitly
named source `control_unaccepted.py image` and `accepted-gate`. Log derivatives
replace only the local source prefix; result.json preserves original log hashes.
[Manifest](manifest.json) binds this public proof. Root owns independent review,
ordinary-history merge, final content remeasurement, transport integration and
any later execution authorization. No queue/release/candidate promotion here.
