const { MongoClient } = require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official/node_modules/mongodb');
const qp = require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-bf-food/lib/food/quickpick');
(async () => {
  const c = new MongoClient('mongodb://127.0.0.1:27018'); await c.connect();
  const col = c.db('probe_readlens').collection('food');
  await col.deleteMany({});
  await col.insertMany([
    {name:'QP-A', type:'quickpick', hidden:'false', position:'1', carbs:10},   // jQuery-written
    {name:'QP-B', type:'quickpick', hidden:false,   position:2,   carbs:20},   // JSON-written
    {name:'QP-C', type:'quickpick',                 position:'10',carbs:30},   // pre-field
    {name:'QP-D', type:'quickpick', hidden:'true',  position:'3', carbs:40},   // hidden
    {name:'QP-E', type:'quickpick', hidden:true,    position:'4', carbs:50},   // hidden (JSON)
    {name:'Plain-1', type:'food', carbs:5}, {name:'Plain-2', type:'food', carbs:6}
  ]);
  const dev = await col.find({ $and:[{type:'quickpick'},{hidden:'false'}]}).sort({position:1}).toArray();
  console.log('dev   GET /api/v1/food/quickpicks ->', dev.map(r=>r.name+'@'+r.position).join(', ') || '(empty)');
  const fixed = (await col.find({ $and:[{type:'quickpick'},{hidden:{$nin:[true,'true']}}]}).toArray()).sort(qp.byPosition);
  console.log('fixed GET /api/v1/food/quickpicks ->', fixed.map(r=>r.name+'@'+r.position).join(', '));
  // client-side boluscalc dropdown, dev logic vs fixed logic, over ddata.food = ALL food
  const all = await col.find({}).toArray();
  const quickpicksDev = all.filter(r=>r.type=='quickpick');
  const optionsDev = all.map((r,i)=>`${i}:${r.name}->loads ${quickpicksDev[i]?quickpicksDev[i].name:'UNDEFINED(throws)'}`);
  console.log('dev   #bc_quickpick options:', optionsDev.join(' | '));
  const sel = qp.selectable(all);
  console.log('fixed #bc_quickpick options:', sel.map((r,i)=>`${i}:${r.name}->loads ${sel[i].name}`).join(' | '));
  await col.drop(); await c.close();
})().catch(e=>{console.error('ERR',e.message);process.exit(1)});
