const PORT = process.argv[2];
const probes = [
  ['count.json no filter',        'entries/count.json?' + new URLSearchParams({})],
  ['count.json sgv$gt150',        'entries/count.json?' + new URLSearchParams({'find[sgv][$gt]':'150'})],
  ['count.json mbg$exists=false', 'entries/count.json?' + new URLSearchParams({'find[mbg][$exists]':'false'})],
  ['count.json type=mbg',         'entries/count.json?' + new URLSearchParams({'find[type]':'mbg'})],
  ['LIST  sgv$gt150 (for parity)','entries.json?' + new URLSearchParams({'find[sgv][$gt]':'150','count':'1000'})],
];
(async () => {
  for (const [label, path] of probes) {
    const r = await fetch(`http://localhost:${PORT}/api/v1/${path}`);
    const t = await r.text(); let d=null; try{d=JSON.parse(t);}catch(e){}
    console.log(String(label).padEnd(32), `http=${r.status}`, Array.isArray(d)?(`n=${d.length} ${JSON.stringify(d).slice(0,70)}`):(d?JSON.stringify(d).slice(0,80):t.slice(0,50)));
  }
})();
