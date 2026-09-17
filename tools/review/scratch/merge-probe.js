const p=process.argv[2];
const rd=require(p+'/lib/client/receiveddata.js');
const ddata={sgvs:[],mbgs:[],treatments:[{_id:'A',mills:1},{_id:'B',mills:2}],food:[],devicestatus:[],profiles:[],processTreatments:function(){},processDurations:function(){}};
const received={delta:true,treatments:[{_id:'A',action:'remove'},{_id:'Z',action:'update',mills:3}]};
try{ rd(received,ddata,{}); console.log('  OK  treatments after merge:',JSON.stringify(ddata.treatments.map(t=>t._id))); }
catch(e){ console.log('  THREW:',e.constructor.name+':',e.message); }
