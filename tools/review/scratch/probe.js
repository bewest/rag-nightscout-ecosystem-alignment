const PORT = process.argv[2] || '1345';
const probes = [
  ['count=10',                      'entries.json?count=10'],
  ['count=1000',                    'entries.json?count=1000'],
  ['count=0 (BF-01)',               'entries.json?count=0'],
  ['count=abc',                     'entries.json?count=abc'],
  ['sgv $gt 150 (BF-02 coercion)',  'entries.json?' + new URLSearchParams({'find[sgv][$gt]':'150','count':'1000'})],
  ['sgv $lt 100',                   'entries.json?' + new URLSearchParams({'find[sgv][$lt]':'100','count':'1000'})],
  ['mbg $exists=false (BF-11)',     'entries.json?' + new URLSearchParams({'find[mbg][$exists]':'false','count':'1000'})],
  ['mbg $exists=true',              'entries.json?' + new URLSearchParams({'find[mbg][$exists]':'true','count':'1000'})],
  ['type=mbg',                      'entries.json?' + new URLSearchParams({'find[type]':'mbg','count':'1000'})],
  ['type=sgv count=10 (in-mem path)','entries.json?' + new URLSearchParams({'find[type]':'sgv','count':'10'})],
];
(async () => {
  for (const [label, path] of probes) {
    try {
      const r = await fetch(`http://localhost:${PORT}/api/v1/${path}`);
      const t = await r.text();
      let d; try { d = JSON.parse(t); } catch (e) { d = null; }
      const shape = Array.isArray(d) ? `n=${d.length}` : (d ? JSON.stringify(d).slice(0,90) : t.slice(0,60));
      console.log(String(label).padEnd(34), `http=${r.status}`, shape);
    } catch (e) { console.log(String(label).padEnd(34), 'ERR', e.message); }
  }
})();
