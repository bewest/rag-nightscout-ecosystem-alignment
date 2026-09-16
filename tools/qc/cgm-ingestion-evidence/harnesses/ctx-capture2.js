'use strict';
const L = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam/lib/';
const fs = require('fs');
const mk = () => require(L + 'language')(fs);

// Two per-tenant language instances with DIFFERENT catalogues.
const langA = mk(); langA.offerTranslations({ 'Urgent': 'A-URGENT' });
const langB = mk(); langB.offerTranslations({ 'Urgent': 'B-URGENT' });

// ---- A6: isolate CAPTURE from catalogue mutation ----
// Plugin init under tenant A's ctx (ar2.js:17 / boluswizardpreview.js:7 shape)
let ctx = { language: langA };
const capturedTranslate = ctx.language.translate;   // captured at INIT

// Now re-point ctx.language per tenant, as a per-tenant ctx must.
ctx = { language: langB };
console.log('A6 ctx.language re-pointed to B. ctx.language.translate("Urgent") =',
  ctx.language.translate('Urgent'));
console.log('A6 but the plugin still calls its CAPTURED translate  =',
  capturedTranslate('Urgent'), ' <-- should be A-URGENT if capture is the defect');

// ---- Non-vacuity: break it. If capture were NOT the mechanism, a plugin that
// re-reads ctx.language.translate per call would follow the re-point. Show it does.
const perCallTranslate = (c, t) => c.language.translate(t);
console.log('NV  a per-call reader on the same re-pointed ctx =',
  perCallTranslate(ctx, 'Urgent'), ' <-- should be B-URGENT');

// ---- A7: levels cannot be re-pointed at all (module shape, not capture) ----
const levels = require(L + 'levels');
const ctxA = { language: langA, levels: require(L + 'levels') };
const ctxB = { language: langB, levels: require(L + 'levels') };
console.log('A7 ctxA.levels === ctxB.levels :', ctxA.levels === ctxB.levels,
  '(a per-tenant ctx cannot hand out two levels objects)');
// bootevent.js:218 shape, run per tenant:
ctxA.levels.translate = ctxA.language.translate;
const afterA = ctxA.levels.toDisplay(2);
ctxB.levels.translate = ctxB.language.translate;   // tenant B boots second
console.log('A7 tenant A toDisplay(2) right after A booted :', afterA);
console.log('A7 tenant A toDisplay(2) AFTER tenant B booted:', ctxA.levels.toDisplay(2),
  ' <-- last tenant to boot wins, process-wide');
