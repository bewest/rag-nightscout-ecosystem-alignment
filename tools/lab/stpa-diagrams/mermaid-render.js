// Render .mmd files in Chrome the way the docs site does: mermaid.js running in the page.
//   node mermaid-render.js <chrome> <file.mmd>...   writes <file>.svg beside each input
// The ELK layout is registered here; Material for MkDocs does not register it.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const NM = path.dirname(require.resolve('mermaid/package.json'));
const ROOTS = {
  '/mermaid/': path.join(NM, 'dist') + '/',
  '/elk/': path.join(path.dirname(require.resolve('@mermaid-js/layout-elk/package.json')), 'dist') + '/',
};

(async () => {
  const [chrome, ...files] = process.argv.slice(2);
  const browser = await chromium.launch({ executablePath: chrome, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  await page.route('http://lab.local/**', (route) => {
    const u = new URL(route.request().url()).pathname;
    if (u === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><body></body>' });
    for (const [pre, dir] of Object.entries(ROOTS)) {
      if (u.startsWith(pre)) {
        return route.fulfill({ contentType: 'text/javascript', body: fs.readFileSync(dir + u.slice(pre.length)) });
      }
    }
    return route.fulfill({ status: 404, body: '' });
  });
  await page.goto('http://lab.local/');
  await page.addScriptTag({ type: 'module', content: `
    import mermaid from '/mermaid/mermaid.esm.min.mjs';
    import elk from '/elk/mermaid-layout-elk.esm.min.mjs';
    mermaid.registerLayoutLoaders(elk);
    mermaid.initialize({ startOnLoad: false, theme: 'default' });
    window.__mermaid = mermaid;` });
  await page.waitForFunction(() => window.__mermaid);
  let failed = 0;
  for (const f of files) {
    const t0 = Date.now();
    const src = fs.readFileSync(f, 'utf8');
    try {
      const svg = await page.evaluate(async (s) => (await window.__mermaid.render('m' + Date.now(), s)).svg, src);
      fs.writeFileSync(f.replace(/\.mmd$/, '.svg'), svg);
      console.log(JSON.stringify({ file: f, ok: true, ms: Date.now() - t0 }));
    } catch (e) {
      failed++;
      console.log(JSON.stringify({ file: f, ok: false, error: String(e).slice(0, 300) }));
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
