'use strict';
// Round 3: preloaded into each arm by reads.js (NODE_OPTIONS=--require). Counts
// the identity reads the naming prototypes make, in the arm's own process: a
// driver find projected to exactly {_id: 1, identifier: 1} (only the
// prototypes issue it), the documents it returned and their BSON bytes.
// Client-side because the database profiler's capped collection (1 MB) drops
// the entry of a large read behind the 1,000 per-operation entries of a
// backfill. IPC: {cmd: 'reads'} -> {cmd: 'reads', tally}.
const path = require('path');
const tree = process.argv[2];
const { Collection, BSON } = require(path.join(tree, 'node_modules/mongodb'));
const find = Collection.prototype.find;
const tally = { queries: 0, docs: 0, bytes: 0 };
const identity = p => !!p && Object.keys(p).length === 2 && p._id === 1 && p.identifier === 1;
Collection.prototype.find = function (filter, options) {
  const cursor = find.apply(this, arguments);
  if (options && identity(options.projection)) {
    tally.queries++;
    const toArray = cursor.toArray.bind(cursor);
    cursor.toArray = async function () {
      const docs = await toArray();
      tally.docs += docs.length;
      for (const d of docs) tally.bytes += BSON.calculateObjectSize(d);
      return docs;
    };
  }
  return cursor;
};
process.on('message', m => { if (m && m.cmd === 'reads') process.send({ cmd: 'reads', id: m.id, tally: Object.assign({}, tally) }); });
