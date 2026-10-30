'use strict';
// Preloaded into each arm (NODE_OPTIONS=--require). Counts every driver find in
// the arm's process: queries, documents returned and their BSON bytes. The
// database profiler cannot do this for bulk calls (its 1 MB capped collection
// drops entries; see tools/lab/commit-event-bench). IPC: {cmd: 'reads'}.
const path = require('path');
const tree = process.argv[2];
const { Collection, BSON } = require(path.join(tree, 'node_modules/mongodb'));
const find = Collection.prototype.find;
const tally = { queries: 0, docs: 0, bytes: 0 };
Collection.prototype.find = function () {
  const cursor = find.apply(this, arguments);
  tally.queries++;
  const toArray = cursor.toArray.bind(cursor);
  cursor.toArray = async function () {
    const docs = await toArray();
    tally.docs += docs.length;
    for (const d of docs) tally.bytes += BSON.calculateObjectSize(d);
    return docs;
  };
  return cursor;
};
process.on('message', m => { if (m && m.cmd === 'reads') process.send({ cmd: 'reads', id: m.id, tally: Object.assign({}, tally) }); });
