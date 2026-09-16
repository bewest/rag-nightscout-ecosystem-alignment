// Arm: does booterror.js's error-line renderer survive a {desc}-only boot error?
const pick = require('./cut4/lib/utils/pick');
function renderLine(obj){
  let message;
  if (typeof obj.err === 'string' || obj.err instanceof String) { message = obj.err; }
  else { message = JSON.stringify(pick(obj.err, Object.getOwnPropertyNames(obj.err))); }
  return '<dt><b>' + obj.desc + '</b></dt><dd>' + message.replace(/\\n/g,'<br/>') + '</dd>';
}
const cases = [
  ['ARM  {desc} only (cut4 bootevent.js:330/335)', {desc:'CONNECT_COUNTRY_CODE is required'}],
  ['CTRL {desc, err:string} (Mongo)',              {desc:'Unable to connect to Mongo', err:'econnrefused'}],
  ['CTRL {desc, err:array} (ENV Error)',           {desc:'ENV Error', err:['a','b']}],
  ['CTRL {desc, err:Error}',                       {desc:'boom', err:new Error('x')}],
  ['ARM  {desc, err:null}',                        {desc:'d', err:null}],
];
for (const [label,obj] of cases){
  try { console.log(label.padEnd(48), '=> OK  ', renderLine(obj).slice(0,70)); }
  catch(e){ console.log(label.padEnd(48), '=> THROW', e.constructor.name+': '+e.message); }
}
