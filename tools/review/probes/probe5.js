const PORT=process.argv[2];
(async()=>{
 for (const [l,p] of [['in-mem path count=10','entries.json?count=10'],['mongo path count=10','entries.json?'+new URLSearchParams({'find[device]':'synthetic://lens','count':'10'})]]) {
   const r=await fetch(`http://localhost:${PORT}/api/v1/${p}`); const j=await r.json();
   console.log(String(l).padEnd(24), 'n='+j.length, 'has mills=', j.length?('mills' in j[0]):'n/a', 'keys=', j.length?Object.keys(j[0]).join(','):'-');
 }
})();
