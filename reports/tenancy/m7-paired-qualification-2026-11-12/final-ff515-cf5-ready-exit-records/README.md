# Retained original phase exit records — 2026-11-12

This is a bounded record-admission supplement to
[the original paired qualification](../final-ff515-cf5-ready/README.md), commit
`e17f4f5f83bd2610be12fb4712398306dd94defd`. No phase, resource action, cleanup or
native check was replayed. The original leaf and its capture hashes are unchanged.

The original tool results were recovered verbatim from host-retained agent-history
blocks embedded in local review transcripts. This is a retained duplicate source;
availability of the primary Exec process datastore is not asserted. The broader
private transcripts are not published. Only the original launch and final poll
calls/results are included, with local source reference, record-line SHA256 and
verbatim block SHA256 in [provenance.json](provenance.json).

| Phase | Original session / final chunk | Explicit process exit_code | Additional original stdout literal |
|---|---|---:|---|
| Stock/restore | 71766 / `574329` | 0 | `stage: stock-restore`, `exit: 0` |
| Settings controls | 47793 / `eb4238` | 0 | Success marker; no separately printed numeric child code |
| Clinical 2→3 | 84437 / `a5e40c` | 0 | `stage: clinical-members2to3`, `exit: 0` |
| Controlled realtime move | 35114 / `faa421` | 0 | `stage: controlled-realtime-move`, `exit: 0` |

[records.json](records.json) derives these numeric values directly from the
retained result metadata and original printed JSON, never from TAP or semantic
success assertions. Session IDs in launch results match the captured final poll
calls. Stock, clinical and move stdout explicitly printed the native fixture
subprocess return code. Settings has an observed tool-managed outer Python process
status: its captured launch call propagated the settings driver's return code,
but no separate numeric inner control-code stdout was retained. That child field
remains null; individual controls include expected refusals and are not asserted
to have all returned zero.

The supplement preserves the original ff515/cf5/image399/nonce identity from the
committed primary capture. It adds no capacity, new execution or broader acceptance
claim. The [executed extraction script](extractor.executed.py) is retained as dated
provenance only; it reads selected local transcript blocks and writes a new
derivative. It must not be replayed into immutable evidence paths.
[sha256.json](sha256.json) pins the bounded derivative bytes. The coordinator owns
which directly observed process or semantic criteria its existing gate admits.
