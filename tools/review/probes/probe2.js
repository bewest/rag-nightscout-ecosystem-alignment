const PORT = process.argv[2];
const q = o => 'entries.json?' + new URLSearchParams(o);
const probes = [
  ['count=0 + device filter (MONGO path)', q({'find[device]':'synthetic://lens','count':'0'})],
  ['count=1 + device filter (control)',    q({'find[device]':'synthetic://lens','count':'1'})],
  ['count=-3 + device filter',             q({'find[device]':'synthetic://lens','count':'-3'})],
  ['count=1e2 + device filter',            q({'find[device]':'synthetic://lens','count':'1e2'})],
  ['sgv $gt 150 + device (mongo path)',    q({'find[device]':'synthetic://lens','find[sgv][$gt]':'150','count':'1000'})],
  ['dateString $exists=false',             q({'find[dateString][$exists]':'false','count':'1000'})],
];
(async () => {
  for (const [label, path] of probes) {
    const r = await fetch(`http://localhost:${PORT}/api/v1/${path}`);
    const t = await r.text(); let d = null; try { d = JSON.parse(t); } catch (e) {}
    console.log(String(label).padEnd(40), `http=${r.status}`, Array.isArray(d) ? `n=${d.length}` : (d?JSON.stringify(d).slice(0,80):t.slice(0,50)));
  }
})();
