const W = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-bf-reads';
let captured = null;
const fakeColl = {
  aggregate: (p) => { captured = p; return { toArray: async () => [] }; },
  find: () => ({ sort: () => ({ limit: () => ({ toArray: async () => [] }), toArray: async () => [] }) })
};
const ctx = { store: { collection: () => fakeColl }, bus: { emit(){} } };
const env = { };

const probes = [
  ['devicestatus', { find: { 'uploader.battery': { $gte: '50' } } }],
  ['entries',      { find: { delta: { $gte: '2' } } }],
  ['treatments',   { find: { duration: { $gte: '30' } } }],
];

(async () => {
for (const [mod, opts] of probes) {
  const storage = require(W + '/lib/server/' + mod + '.js');
  const api = storage(env, ctx);
  captured = null;
  await new Promise(res => api.aggregate(JSON.parse(JSON.stringify(opts)), () => res()));
  const match = captured && captured[0] && captured[0].$match;
  const field = Object.keys(opts.find)[0];
  console.log(mod.padEnd(14), field.padEnd(20), 'count $match ->', JSON.stringify(match && match[field]));
}
})();
