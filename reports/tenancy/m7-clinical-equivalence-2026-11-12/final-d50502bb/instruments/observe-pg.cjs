'use strict';
const pg = require(process.env.CRM_ROOT + '/node_modules/pg');
let queries = 0, connects = 0;
for (const name of ['query', 'connect']) {
 const original = pg.Pool.prototype[name];
 pg.Pool.prototype[name] = function (...args) { if (name === 'query') queries++; else connects++; return Reflect.apply(original, this, args); };
}
process.on('exit', () => process.stderr.write(JSON.stringify({pgPoolQueries: queries, pgPoolConnects: connects}) + '\n'));
