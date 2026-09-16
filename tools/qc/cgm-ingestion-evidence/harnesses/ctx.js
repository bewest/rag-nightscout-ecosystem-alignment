const path='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam/lib/';
const l1=require(path+'levels'), l2=require(path+'levels');
console.log('levels singleton (require twice, ===):', l1===l2);
const langFactory=require(path+'language');
console.log('language.js exports a function (factory):', typeof langFactory==='function');
const A=langFactory(), B=langFactory();
console.log('two language instances distinct:', A!==B);
A.offerTranslations({'Urgent':'A-URGENT'}); A.set('en');
B.offerTranslations({'Urgent':'B-URGENT'}); B.set('en');
// simulate bootevent.js:212 per tenant
const ctxA={levels:require(path+'levels'), language:A};
ctxA.levels.translate=ctxA.language.translate;
const capturedByPluginA = ctxA.levels;              // plugin captures ctx.levels at init
console.log('tenant A toDisplay(2) right after A booted:', capturedByPluginA.toDisplay(2));
const ctxB={levels:require(path+'levels'), language:B};
ctxB.levels.translate=ctxB.language.translate;
console.log('ctxA.levels === ctxB.levels:', ctxA.levels===ctxB.levels);
console.log('tenant A toDisplay(2) after tenant B booted:', capturedByPluginA.toDisplay(2));
// capture vs per-call for language
const cap=A.translate;
A.offerTranslations({'Urgent':'MUTATED'}); A.set('en');
console.log('captured translate after offerTranslations:', cap('Urgent'));
