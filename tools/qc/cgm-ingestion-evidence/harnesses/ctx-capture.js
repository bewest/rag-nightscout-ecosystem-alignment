'use strict';
const path = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam/lib/';
const fs = require('fs');

// A1: is levels a require-cache singleton shared by every ctx?
const levelsA = require(path + 'levels');
const levelsB = require(path + 'levels');
console.log('A1 levels singleton (levelsA === levelsB):', levelsA === levelsB);

// A2: does levels own a PRIVATE language instance, distinct from any ctx.language?
const langForTenantA = require(path + 'language')(fs);
const langForTenantB = require(path + 'language')(fs);
console.log('A2 two ctx languages are distinct instances:', langForTenantA !== langForTenantB);
console.log('A2 levels.language is neither of them:',
  levelsA.language !== langForTenantA && levelsA.language !== langForTenantB);

// A3: plugin-init capture. Simulate plugins/simplealarms.js + ar2.js:
//     var levels = ctx.levels;  var translate = ctx.language.translate;
const ctxA = { language: langForTenantA, levels: levelsA };
const capturedLevelsA   = ctxA.levels;              // simplealarms.js:14
const capturedTranslateA = ctxA.language.translate;  // ar2.js:17

// Now build a per-tenant ctx for B that RE-POINTS both, as a per-tenant ctx would have to.
const ctxB = { language: langForTenantB, levels: levelsB };
console.log('A3 re-pointing ctx.levels gives a DIFFERENT object:', ctxA.levels !== ctxB.levels);

// A4: does a captured translate follow a set() on its OWN instance?
langForTenantA.offerTranslations({ 'Urgent': 'ORIGINAL' });
const before = capturedTranslateA('Urgent');
langForTenantA.set('de');
const afterSet = capturedTranslateA('Urgent');
langForTenantA.offerTranslations({ 'Urgent': 'MUTATED' });
const afterOffer = capturedTranslateA('Urgent');
console.log('A4 captured translate: before=%j afterSet(de)=%j afterOfferTranslations=%j',
  before, afterSet, afterOffer);

// A5: does mutating tenant A's language reach tenant B's, or levels'?
console.log('A5 tenant B translate of same key:', langForTenantB.translate('Urgent'));
console.log('A5 levels.translate of same key:', levelsA.translate('Urgent'));
console.log('A5 levels.toDisplay(2):', levelsA.toDisplay(2));
