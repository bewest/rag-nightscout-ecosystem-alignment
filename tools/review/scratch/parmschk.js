// Re-implements ONLY the two queryParms bodies, lifted verbatim from each branch,
// because the surrounding init() needs jQuery + DOM.
function dev(search){ var params={}; var location={search:search};
  if ((typeof location !== 'undefined') && location.search) {
    location.search.substr(1).split('&').forEach(function(item){
      params[item.split('=')[0]] = item.split('=')[1].replace(/[_\+]/g,' ');
    });
  } return params; }
function fixed(search){ var params={}; var location={search:search};
  if ((typeof location !== 'undefined') && location.search) {
    location.search.substr(1).split('&').forEach(function(item){
      if (!item) { return; }
      var parts = item.split('=');
      params[parts[0]] = (parts.length > 1 ? parts[1] : '').replace(/\+/g,' ');
    });
  } return params; }
const cases = ['?debug', '?token=synthetic_subject-0000000000000000&', '?', '?token=ab-1234567890abcdef', '?mute=true&debug', '?a=1&&b=2'];
for (const c of cases){
  let d,f;
  try { d = JSON.stringify(dev(c)); } catch(e){ d = 'THROWS: '+e.message; }
  try { f = JSON.stringify(fixed(c)); } catch(e){ f = 'THROWS: '+e.message; }
  console.log(c.padEnd(38), '\n   dev  :', d, '\n   fixed:', f);
}
