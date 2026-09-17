const root = process.argv[2];
const rd = require(root + '/lib/client/receiveddata');
function cached(){ return [
  {_id:'a', mills: 1000}, {_id:'b', mills: 2000}, {_id:'c', mills: 3000}
];}
// delta carrying: remove of 'b' (present), then remove of 'zz' (NOT in the browser's cache)
const received = [ {_id:'b', action:'remove'}, {_id:'zz', action:'remove'} ];
try {
  const out = rd.mergeTreatmentUpdate(true, cached(), received);
  console.log(root.split('/').pop(), 'OK ->', out.map(t=>t._id).join(','));
} catch (e) {
  console.log(root.split('/').pop(), 'THROWS ->', e.constructor.name + ': ' + e.message);
}
// second shape: remove present, then update for an _id not cached
const received2 = [ {_id:'b', action:'remove'}, {_id:'zz', action:'update', mills: 4000} ];
try {
  const out = rd.mergeTreatmentUpdate(true, cached(), received2);
  console.log(root.split('/').pop(), 'OK2 ->', out.map(t=>t._id).join(','));
} catch (e) {
  console.log(root.split('/').pop(), 'THROWS2 ->', e.constructor.name + ': ' + e.message);
}
