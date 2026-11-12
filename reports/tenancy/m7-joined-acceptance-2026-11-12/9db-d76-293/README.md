# Joined M7 application acceptance — 2026-11-12

**Locally accepted for the recorded functional scope.** Core `9db0ce94f072c8f34aab889f0181afa4269a6758`, deployment `d76ef17878edb610cdeae75aeef9c07f94b60753`, image `sha256:293a5c531faac6c156305159246e39defd2592612c302af275efe807102a6d3e`. Selected measurement source is alignment `df18100cf13780cec904a792b2bb1ab8867bfb54`, instrument `63844506159ee61f2335d8e94694a21cc48bc558b36f8146d8eb968ebdfa4f6d`/40 files, receipt gate `316a3747e86dd519c8ce302055873903e564862a590cd8e38c4d5bea3b6e7b86`. This records branch acceptance, not a dev merge, operator release or production M7 promotion.

The coordinator independently approved the nonempty policy:29 required criteria and four actual semantic baseline/red/restored triplets, with81 independently hash-verified artifact pins. [Expected policy](expected.json) SHA256 `5b763082da670dac63827e49bf27e8734bb6558ce9aaacb17c4be1fc1b8b94ff`; [receipt](receipt.json) SHA256 `8ea82712ded0eeef9ffede2af3a5ecaec0dbda30c64b69f69b5eb3dfada0c7a7`. The [actual read-only gate result](recorded-gate.txt) is PASS, `RECORDED_EVIDENCE_ONLY`, claims only `acceptance`. [Coordinator approval](coordinator-approval.json) also recomputes the current strict TIME proof independently; this is not a fabricated result or an inferred process exit.

## Actual source and native evidence

- [Core H](../../core-h-acceptance-2026-11-12/README.md) passes all eight default tiers and the full selected86-suite corpus:839 passing, one optional benchmark pending, zero failures. H retains its actual9db/d76/5d7/7209 execution tuple, verified cleanup and nested execution-accounting red-control context. It is not relabeled to the later admission instrument.
- [Current primary image](../../m7-paired-qualification-2026-11-12/primary-9db-d76-guard/README.md) passes exact API×tenant readiness, positive settings setup and clinical2→3 membership with three accepted normal effects, zero cancelled effects/accepted clears, stable B socket/checkpoint and1136ms handoff under30000ms. Its build/clinical provenance stays5d7/52;18 direct phase exits include successful image export.
- The [first current TIME capture](../../evaluator-trusted-scheduling-2026-11-12/native-9db-d76-guard-unmeasured/README.md) remains UNMEASURED: after a captured20-minute engineering hold, the finite10-minute alarm-data episode had no declared due work. It was never changed to a quiet PASS or called a scheduler stall. A [separate fresh-ingestion experiment](../../evaluator-trusted-scheduling-2026-11-12/native-9db-d76-fresh-ingestion/README.md), on the same image, used one same-value current-date synthetic input per tenant through normal shipping HTTP. Actual acquisitions and finite due were observed before one new strict capture:38 successful TIME completions, minimum19 per owner, zero failed completions, direct supervisor0. No settings, baseline seed/plugin, cadence, clock or membership changed.
- Root independently streamed the exact284444672-byte archive, SHA256 `4eb4e791f5c2fa0cce8ad135cf02cfa2723e869d2b465555681d657f92559461`, and verified its Config digest/image ID, linux/amd64, source labels and nonsecret image environment. Archive transfer/import and capacity observations remain separately measured.
- [Final prcheck](prcheck-summary.json) returned0 after full application and applicable native checks; core remained9db, clean, with freshly fetched official/dev `4a482627bfdafb1fef8dcbe0ac6c484811cae563` already contained. No push or source change followed.

Older stock/restore, controlled realtime movement, settings-refusal, synthetic-provider/pinned-client and clinical memory-projection criteria keep their original executed source/image/environment. The [affected-input review](../../m7-unit-repairs-2026-11-12/fixture-source-closure/README.md) and [admission-only instrument review](../../m7-unaccepted-measurement-2026-11-12/independent-review/README.md) state why the narrow reuse applies. No older execution is relabeled. Original memory-only/zero-Pool and full-message cross-schedule differences remain; native identity uses its recorded synthetic provider and Node/browser versions.

## Pending cases and claim limits

Default integration's836 pending comprise834 deferred functional bodies, the separately enabled commit-clock performance benchmark and one unchanged legacy mixed-validity timeout skip. The same-source enabled corpus executes its functional cases and keeps only that named optional benchmark pending. Unit retains one absent external VIEWS_CORPUS_DIR case; dependency retains two absent-consumer applicability cases. Pending never means passing; the legacy gap remains unmeasured. The receipt grants no capacity, real-IdP, Android, HA, production readiness or missed-alarm replay claim.

Some original worker/log/process artifacts remain private because they contain execution-local connection/environment details. The public policy/receipt retain their exact pins; the complete private evidence bundle is required to rerun the full gate. Public H/native records are bounded projections with provenance, not replacements for those original bytes. Using the retained bundle:

```bash
python3 tools/queue/gates/m7_joined_receipt.py \
  --expected reports/tenancy/m7-joined-acceptance-2026-11-12/9db-d76-293/expected.json \
  --receipt reports/tenancy/m7-joined-acceptance-2026-11-12/9db-d76-293/receipt.json \
  --evidence-root "$M7_EVIDENCE_ROOT" --scope acceptance
```

The private bundle and local unpushed ownership are in the [evolving handoff](../../../../externals/work/HANDOFF-m7-join-2026-11-11.md). The main checkout and peer work are untouched.
