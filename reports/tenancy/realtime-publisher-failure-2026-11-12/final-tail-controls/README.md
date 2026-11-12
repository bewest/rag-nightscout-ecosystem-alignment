# Final awaited-tail controls and host-source attestation

Captured 2026-11-12. Host/fixture follow-up
`c10ade28f6e411919a8aa8abc29beefb15c9bc94`, parent
`9c889035eea93fbfff7ae373bee9054776f65625`. No core product change, live action,
new stack, replay, recovery, reset or native image build occurred. The
[original move failure](../original-and-controls/README.md) remains FAIL /
UNCLASSIFIED; this control does not attribute its cause or retroactively pass it.

Independent review reproduced a draft9c final-tail false-PASS: a last complete
probe count was followed by awaited census/omitted-idle probes; a duplicate
received during those awaits was not revalidated. The repaired fixture takes a
fresh exact complete verdict, B exact-session and single-connection assertions
AFTER every awaited census probe, immediately before PASS, with no async gap.
Latest typed probe counts are retained. Readiness, map publication, maintenance
pin, checkpoint, session meaning, source authority and deadlines are unchanged.

The test executes the shipping fixture's actual extracted tail using recording
census/filesystem ports, actual source effectIdentity and no Docker/SQL/startup.
[Original9c red](captures/original-9c-tail-red.log): duplicateB, cold, wrong slot,
changed B session and reconnect injected during the last await each wrongly
returned rather than rejecting (`Missing expected rejection`). Its positive
final-count-retention assertion also failed because those final counts did not
exist. [Follow-up green](captures/followup-controls-green.log):24 checks pass,
zero skipped, including those exact late-event controls plus existing host
error/stream/privacy/nonce/client controls. The fixture's final synchronously
captured verdict rejects those changes while allowing unrelated clinical data
without probe credit. This is a reproduced instrument defect, not an original
publisher or product cause claim.

Bounded LIFECYCLE_* source codes now remain typed; arbitrary messages and oversized
codes remain unclassified. The unsafe-diagnostic-directory control uses explicit
chmod0755 so a restrictive umask cannot accidentally make its negative fixture
safe. Private raw diagnostics remain host-only0700/0600, outside the shared
placement directory. No authority/recovery/refusal semantics changed.

[Final affected tests](captures/affected-green.log):48pass/0fail,14 explicitly
unselected Docker-native platform tests. Existing owned process simulations
remain distinct from real application/PG/publication proof. No comprehensive
source/browser/corpus/capacity acceptance is claimed.

## Minimal isolated pure compatibility recipe

[Isolated archives](captures/isolated-pure-inputs.json) of c10 binding subtree plus
ONLY core47b `lib/tenant-notifications/contract.js` pass the exact four pure files:
[24pass/0skip](captures/isolated-pure-green.log) on Nodev22.23.4. Environment contains
only PATH/TMPDIR/NS_UI_TEST_CORE. No npm, node_modules, dependency overlay, Docker,
native feature flag, service process or live query is required. The contract's
only import is node:crypto. This supplies a bounded independent Node24 host
process/stream/fs compatibility scope; Node24 itself was NOT measured here.
Exclude replacement-recovery/platform suites from that pure scope.

The [host-source attestation](captures/host-source-attestation.json) pins controller,
observation, shipping fixture, private mounted probe/contract/client observer and
tail-test hashes. It is explicitly separate from original runtime47b/be952/image
6138 labels and proof. Native build/qualification stays held for the coordinator's
coherent source/instrument join and one fresh-state boundary. Current uncertain
journal/maps/containers and original evidence remain intact.

Capture hashes: [sha256.json](sha256.json).
