const root = process.argv[2];
const FP = require(root + '/lib/api3/shared/fieldsProjector');
const doc = () => ({ _id:'x', date: 1, device:'d',
  openaps: { suggested: { bg: 120, IOB: 1.2, reason:'lots of text' }, iob: { iob: 1.2 } },
  pump: { battery: { percent: 90 } } });
for (const spec of ['openaps.suggested.bg', 'openaps', 'date,openaps.iob.iob']) {
  const p = new FP(spec);
  const d = doc();
  p.applyProjection(d);
  console.log(root.split('/').pop(), `fields=${spec}`.padEnd(30), '->', JSON.stringify(d), ' storageSpec=', JSON.stringify(p.storageProjection && p.storageProjection()));
}
