# Evaluator hot-file read and parse fixture repair

**Reproduced fixture defect; fixed on local core `dfc3e6b8466b7fcb09d1adf5021c9616b9c9c781`.** The [second unit campaign](../../m7-core-acceptance-2026-11-12/second-unit-campaign/README.md) reached this sole failure on `d50502bb6126bda2bb0af384569e1d95de114f2f`. Runtime source is unchanged by this commit; only `tests/evaluator-preview-runtime.test.js` changes.

The old test named an `fs.openSync` counter “parses” and required one open across repeated reads. The actual legacy hot-file policy is bounded read-through on every call, with JSON parsing reused until bytes change. The revised fixture counts opens and `JSON.parse` of the exact configuration bytes independently: 21 calls perform 21 new bounded reads and retain one parse including boot; a same-size edit changes identity immediately and makes the second parse.

| Measured check | Result |
|---|---|
| Original isolated file | [16 passing, 1 failing, 21 != 1](before.log) |
| Repaired isolated file | [17 passing](after.log) |
| Disable parse reuse in memory | [RED, 22 actual parses != 1](parse-control.log) |
| Freeze current config at boot in memory | [RED, edit identity unchanged and 0 reads != 21](freshness-control.log) |
| Restore unchanged source | [17 passing](restored.log) |
| Exact four adjacent suites | [52 passing](exact-restored.log) |
| Affected file lint | [Exit 0](lint.log) |

The [control instrument](control.cjs) matches one exact source fragment before replacing it in the Node module loader; no product file is changed. The initial adjacent-suite command named a nonexistent `tests/evaluator-config.test.js`; its 50 passing tests and warning remain in `restored.log` and do not establish that missing file's coverage. The corrected four-suite result is the 52-test capture. [Capture digests](SHA256SUMS) preserve both observations. These are source/fixture checks, not PostgreSQL, browser, full-suite or capacity acceptance.
