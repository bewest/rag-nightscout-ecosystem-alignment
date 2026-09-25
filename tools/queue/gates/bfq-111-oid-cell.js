'use strict';
/*
 * bfq-111-oid-cell.js — BF-111, one tools/lab/object-id cell (P-ID-11).
 *
 * find[_id][$in] named each 24-hex id only as the ObjectId it spells, so a
 * record stored with the string _id (15.0.6 and earlier, or a copy from
 * another site) was missing from a read by list and left behind by a bulk
 * DELETE by list, on 15.0.8, dev and #8758 before the fix. The fix
 * (lib/server/query.js) names each 24-hex id in a $in or $nin list in both
 * forms.
 *
 * The gate runs P-ID-11 against --build and passes when a list of one
 * string-stored and one ObjectId-stored treatment reads back both (n=2) and
 * its DELETE leaves neither. The control cell is the same list of two
 * ObjectId-stored treatments, which every build finds and deletes; if it does
 * not, the harness is wrong (CONTROL-INVALID, exit 90).
 *
 *   node tools/queue/gates/bfq-111-oid-cell.js --build <worktree> [--ref <commit>]
 *
 * Green on ab7b22d6; its control is 15.0.8 92d08342, which must be red.
 * Needs docker and `n`; about 20 s. See _oid-cell.js.
 */
const { report } = require('./_gate');
const { args, runCells, cellFindings } = require('./_oid-cell');

const opts = args();
const res = runCells(opts, ['P-ID-11']);
report('bfq-111-oid-cell (BF-111, P-ID-11) ' + res.head, cellFindings(res, {
  'P-ID-11 GET find[_id][$in] [string, OID]': 'n=2',
  'P-ID-11 DELETE find[_id][$in] [string, OID]': '200 / string n=0 / OID n=0'
}, {
  'P-ID-11 GET, DELETE find[_id][$in] [OID, OID] (control)': 'n=2 / 200 / n=0 / n=0'
}, 'BF-111'));
