'use strict';
/*
 * bfq-109-oid-cell.js — BF-109, one tools/lab/object-id cell (P-ID-10).
 *
 * On #8758 before the fix (6d120fa2) an API v3 DELETE or PUT by identifier,
 * where a v1 record {_id: X} and the v3 copy {identifier: X} an earlier v3 PUT
 * added both exist, wrote the v1 half: DELETE answered 200 and GET still showed
 * the record; PUT left two documents with identifier X. The fix (modify.js
 * writeFilter) writes the document the read returns.
 *
 * The gate runs P-ID-10 against --build and passes when every write cell reads
 * as the fixed build (and as 15.0.8 and dev, which never had BF-109):
 *   "... DELETE, then GET" = 200 / v1-original[(invalid)],v3-copy(invalid) / GET 410
 *                            (the v1 half is marked too once BF-117 is in)
 *   "... PUT"              = 200 / v1-original,v3-put / identifier=X n=1
 * for a hex and a non-hex identifier. The "GET returns" cells are the control:
 * every build answers them the same, so a difference there means the harness,
 * not the build, is wrong (CONTROL-INVALID, exit 90).
 *
 *   node tools/queue/gates/bfq-109-oid-cell.js --build <worktree> [--ref <commit>]
 *
 * Green on ab7b22d6; its control is 6d120fa2, which must be red.
 * Needs docker and `n`; about 20 s. See _oid-cell.js.
 */
const { report } = require('./_gate');
const { args, runCells, cellFindings } = require('./_oid-cell');

const opts = args();
const res = runCells(opts, ['P-ID-10']);
const expect = {};
const controls = {};
for (const kind of ['hex', 'non-hex']) {
  controls['P-ID-10 ' + kind + ' GET returns'] = '200 / v3-copy';
  // BF-109 is the v3 copy staying valid (GET 200) after DELETE. Whether the
  // v1 half is also marked is not BF-109: it stays valid on 15.0.8, dev and
  // ab7b22d6, and BF-117 (v3 DELETE removes every stored form) marks it too.
  expect['P-ID-10 ' + kind + ' DELETE, then GET'] = /^200 \/ v1-original(\(invalid\))?,v3-copy\(invalid\) \/ GET 410$/;
  expect['P-ID-10 ' + kind + ' PUT'] = '200 / v1-original,v3-put / identifier=X n=1';
}
report('bfq-109-oid-cell (BF-109, P-ID-10) ' + res.head, cellFindings(res, expect, controls, 'BF-109'));
