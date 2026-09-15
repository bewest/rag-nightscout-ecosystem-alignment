// Can the AST express what API v1 actually produces?
// The shapes below are lib/server/query.js's real output, captured by running it
// (see the execution plan §3.4). Each is hand-mapped to the AST; anything that
// cannot be mapped is a gap that T1.2 has to resolve, not a detail.
'use strict';
const { validate, toMongo } = require('./filter-ast');
const isDeepStrictEqual = require('util').isDeepStrictEqual;

const CASES = [
  ['implicit equality',      {type:'sgv'},                         {op:'eq',field:'type',value:'sgv'}],
  ['injected date bound',    {date:{$gte:1789}},                   {op:'gte',field:'date',value:1789}],
  ['range on one field',     {sgv:{$gte:100,$lte:200}},            {op:'and',nodes:[{op:'gte',field:'sgv',value:100},{op:'lte',field:'sgv',value:200}]}],
  ['two fields',             {type:'sgv',date:{$gte:1789}},        {op:'and',nodes:[{op:'eq',field:'type',value:'sgv'},{op:'gte',field:'date',value:1789}]}],
  ['top-level $or',          {$or:[{sgv:{$lt:70}},{sgv:{$gt:180}}]},{op:'or',nodes:[{op:'lt',field:'sgv',value:70},{op:'gt',field:'sgv',value:180}]}],
  ['dotted path',            {'uploader.battery':{$lt:50}},        {op:'lt',field:'uploader.battery',value:50}],
  ['$ne null',               {carbs:{$ne:null}},                   {op:'ne',field:'carbs',value:null}],
  ['$in',                    {type:{$in:['sgv','mbg']}},           {op:'in',field:'type',value:['sgv','mbg']}],
  ['$exists',                {insulin:{$exists:true}},             {op:'exists',field:'insulin',value:true}],
  ['$regex',                 {eventType:{$regex:'^Temp'}},         {op:'re',field:'eventType',value:'^Temp'}],
];
// Not filters at all — identifier lookups. Listed so they are not mistaken for gaps.
const IDENTIFIER_CASES = [
  ['_id single',  {_id:'5f8d0d55b54764421b7156c3'}],
  ['_id $in',     {_id:{$in:['5f8d0d55b54764421b7156c3','5f8d0d55b54764421b7156c4']}}],
];

let ok=0, gaps=[];
console.log('v1 shape                    expressible  round-trips to same Mongo filter');
console.log('-'.repeat(78));
for (const [label, v1, ast] of CASES) {
  let expressible=true, note='';
  try { validate(ast); } catch(e) { expressible=false; note=e.message; }
  const round = expressible ? toMongo(ast) : null;
  // Semantic equality, not syntactic: the AST emits {$and:[{a:{$gte:1}}]} where
  // v1 emits {a:{$gte:1}}. Both are the same query; compare via mingo instead.
  const { Query } = require('mingo');
  const probe = [
    {type:'sgv',date:1789,sgv:150,carbs:5,insulin:1,eventType:'Temp Basal',uploader:{battery:40}},
    {type:'mbg',date:1000,sgv:60,uploader:{battery:90}},
    {type:'cal',date:2000,sgv:200},
    {date:1789},
    {},
  ];
  let same=false;
  if (expressible) {
    const a=new Query(v1), b=new Query(round);
    same = isDeepStrictEqual(probe.filter(d=>a.test(d)), probe.filter(d=>b.test(d)));
  }
  if (expressible && same) ok++; else gaps.push([label, note || 'semantics differ']);
  console.log(`${label.padEnd(27)} ${String(expressible).padEnd(12)} ${same}`);
}
console.log('\nidentifier lookups (not filters — resolved by identifier opacity, §4.1 rule 2):');
for (const [label, shape] of IDENTIFIER_CASES) console.log(`  ${label.padEnd(14)} ${JSON.stringify(shape)}`);
console.log(`\n${ok}/${CASES.length} v1 filter shapes expressible AND semantically identical`);
if (gaps.length) { console.log('GAPS:'); gaps.forEach(([l,n])=>console.log(`  ${l}: ${n}`)); process.exit(1); }
