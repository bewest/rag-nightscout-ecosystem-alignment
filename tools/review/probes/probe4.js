const PORT = process.argv[2];
const probes = [
  ['/count/entries/where  (no filter)',      'count/entries/where'],
  ['/count/entries/where sgv$gt150',         'count/entries/where?' + new URLSearchParams({'find[sgv][$gt]':'150'})],
  ['/count/entries/where mbg$exists=false',  'count/entries/where?' + new URLSearchParams({'find[mbg][$exists]':'false'})],
  ['/count/entries/where type=mbg',          'count/entries/where?' + new URLSearchParams({'find[type]':'mbg'})],
  ['/count/entries/where date$gte 24h',      'count/entries/where?' + new URLSearchParams({'find[date][$gte]': String(Date.now()-86400000)})],
];
(async () => {
  for (const [label, path] of probes) {
    const r = await fetch(`http://localhost:${PORT}/api/v1/${path}`);
    const t = await r.text(); let d=null; try{d=JSON.parse(t);}catch(e){}
    console.log(String(label).padEnd(40), `http=${r.status}`, d?JSON.stringify(d).slice(0,110):t.slice(0,60));
  }
})();
