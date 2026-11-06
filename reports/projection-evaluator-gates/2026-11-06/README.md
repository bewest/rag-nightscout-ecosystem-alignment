# Recovered clinical projection: native semantic controls

Reproduced on archived application `1990f453e09303d9dcf3394f0f50a42c3ce4052b`
with alignment gate instrument `2d7ea7a3c95ae924745b9e9d66d2af33371a21f3`.
The granted slot executed exactly two native controls, then one fresh restoration.
The joined campaign's earlier seven-case positive remains separate; it was not
repeated before these controls. Synthetic data only.

| Run | Native result | Required symptom |
|---|---|---|
| Identity control | 0 passing / 0 pending / 1 failing | Physical two-row/two-kind assertions pass first; clinical reading is **111 instead of 222** |
| Bootstrap control | 0 / 0 / 1 | Independently stored reading123 exists first; recovered clinical reading is **undefined instead of123** |
| Fresh restoration | **7 / 0 / 0** | Complete prepared evaluator cohort passes |

Both red failures are explicit `ERR_ASSERTION` results with their named clinical
messages. Strict classification requires the one selected test, expected native
exit, exact symptom and no pending cases. Import/setup/SQL/timeout/TypeError or
unrelated assertion failures cannot establish a semantic red. No runtime or
classifier mismatch occurred in this slot.

Identity removes only `id_kind` from the actual durable replay map key. The
clinical computation then loses the newest ObjectId reading while the independent
physical rows retain both identities. Bootstrap replaces the full-bootstrap lower
bound with the advanced previous checkpoint, losing an independently stored
current reading when the projection is empty. Each invocation starts from a
fresh whole-source archive with lockfile-matched private dependencies; source
worktrees are never changed. Restoring the product source restores all seven
native cases, including independent physical-table property comparisons, retained
A/B results, downstream failure/retry, explicit later-time reevaluation and actual
producer death after commit before publication.

The gate applies one **scratch-only test-oracle adaptation** consistently to all
three archives: the clinical123 assertion accesses `bgnow?.mean` rather than
`bgnow.mean`. It still requires123. This makes an absent clinical object produce
the intended explicit assertion instead of an unrelated TypeError; no positive
semantics or product code is changed by this adaptation. The native fixture's
existing physical-row oracles are unchanged and precede the clinical assertions.

Commands, from the owned alignment gate worktree with explicit repository and
matching dependency paths:

```bash
node tools/queue/gates/multitenant-next-slices.js --suite projection-evaluator \
  --ref 1990f453e09303d9dcf3394f0f50a42c3ce4052b --control identity
node tools/queue/gates/multitenant-next-slices.js --suite projection-evaluator \
  --ref 1990f453e09303d9dcf3394f0f50a42c3ce4052b --control bootstrap
node tools/queue/gates/multitenant-next-slices.js --suite projection-evaluator \
  --ref 1990f453e09303d9dcf3394f0f50a42c3ce4052b
```

All three owned PostgreSQL16 containers and their three exact captured mounted
volumes were verified absent by the gate, then independently re-inspected. The
host retained its462-volume baseline; old unknown services were preserved.
Runtime claimed22:46:40Z and **released22:48:29Z**. The image digest, exact
resources, native reports and raw-artifact hashes are retained in
[summary](summary.json), [cleanup](independent-cleanup.json),
[public artifact index](artifact-index.json) and
[private raw artifact index](private-artifact-index.json).
Public logs replace only machine-local alignment prefixes; private originals
remain available for exact hash verification.

Source syntax/help/strict mutation-classifier tests passed. Classifier tests are
instrument checks, not extra application runtime cases. Lint reports zero errors
and25 dynamic filesystem warnings. No broad alignment, full/browser/corpus,
prcheck, publication, source/schema/default change or role enablement ran here.
These controls support bounded **current-row clinical projection recovery**;
they do not complete M5 or establish scheduling, durable notification handoff,
ack/snooze, intermediate-event history, provider delivery, exactly-once effects,
performance or the separate socket data-write contract.
