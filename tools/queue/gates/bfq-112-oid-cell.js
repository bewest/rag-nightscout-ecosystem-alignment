'use strict';
/*
 * bfq-112-oid-cell.js — BF-112 (the remove half), one tools/lab/object-id cell (P-ID-12).
 *
 * Up to 15.0.8, creating an auth subject with a client's 24-hex _id stored it
 * as the string, and DELETE /api/v2/authorization/subjects/<that hex> removed
 * only an ObjectId _id: it answered 200 and the subject, with its access,
 * stayed. Since #8754 create keeps only a subject's owned fields, so no new
 * string _id is stored; subjects stored that way before remain. The fix
 * (lib/authorization/storage.js remove) matches either form.
 *
 * The gate seeds a subject with a string _id straight into mongo (as 15.0.8's
 * create left it), deletes it by that hex through the API, and passes when it
 * is gone. The control cell is a subject stored with an ObjectId _id, which
 * every build deletes; if it does not, the harness is wrong (CONTROL-INVALID,
 * exit 90).
 *
 *   node tools/queue/gates/bfq-112-oid-cell.js --build <worktree> [--ref <commit>]
 *
 * Green on ab7b22d6; its control is 15.0.8 92d08342, which must be red.
 * Needs docker and `n`; about 20 s. See _oid-cell.js.
 */
const { report } = require('./_gate');
const { args, runCells, cellFindings } = require('./_oid-cell');

const opts = args();
const res = runCells(opts, ['P-ID-12']);
report('bfq-112-oid-cell (BF-112 remove, P-ID-12) ' + res.head, cellFindings(res, {
  'P-ID-12 legacy string subject DELETE by its hex': '200 / n=0'
}, {
  'P-ID-12 legacy OID subject DELETE by its hex (control)': '200 / n=0'
}, 'BF-112'));
