const path=require('path'); const ROOT=process.argv[2];
const find_options = require(path.join(ROOT,'lib','server','query.js'));
const authOpts = { dateField:'created_at', noDateFilter:true };
const cases = {
  'empty find'            : {},
  'by name'               : { name: 'someuser' },
  'with a date field'     : { date: '1700000000000' },
  'with an sgv field'     : { sgv: '120' }
};
for (const [label, find] of Object.entries(cases)) {
  const q = find_options({ find: JSON.parse(JSON.stringify(find)) }, Object.assign({},authOpts));
  const hasDateBound = Object.prototype.hasOwnProperty.call(q,'created_at');
  console.log(('  '+label).padEnd(26), JSON.stringify(q), hasDateBound ? '  <<< DATE BOUND ADDED' : '');
}
