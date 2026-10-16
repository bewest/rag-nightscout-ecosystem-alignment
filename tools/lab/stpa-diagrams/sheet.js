// Contact sheet: every base render of each diagram side by side, as HTML and PNG.
//   node sheet.js <build dir> <chrome> <out dir>
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const [BUILD, CHROME, OUT] = process.argv.slice(2);
const VARIANTS = ['control-grid', 'dot-spline', 'dot-ortho', 'd2-dagre', 'd2-elk', 'd2-grid', 'mermaid-dagre',
  'mermaid-elk', 'plantuml', 'control-random'];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1800, height: 1000 } });
  for (const dia of fs.readdirSync(BUILD).filter((d) => fs.statSync(path.join(BUILD, d)).isDirectory()).sort()) {
    for (const mode of ['base', 'mutated']) {
      const cells = VARIANTS.map((v) => {
        const f = path.join(BUILD, dia, mode, v + '.svg');
        const body = fs.existsSync(f) ? fs.readFileSync(f, 'utf8').replace(/<\?xml[^>]*>/, '') : '<p>no render</p>';
        return `<figure><figcaption>${v}</figcaption><div class="c">${body}</div></figure>`;
      }).join('\n');
      const html = `<!doctype html><meta charset="utf-8"><title>${dia} ${mode}</title><style>
        body{font:13px Helvetica,sans-serif;margin:12px;background:#fff}
        .g{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
        figure{margin:0;border:1px solid #ccc;padding:6px}
        figcaption{font-weight:bold;margin-bottom:4px}
        .c svg{max-width:100%;height:auto;max-height:640px}
        </style><h2>${dia} (${mode})</h2><div class="g">${cells}</div>`;
      const file = path.join(OUT, `${dia}-${mode}.html`);
      fs.writeFileSync(file, html);
      await page.goto('file://' + path.resolve(file));
      await page.waitForTimeout(300);
      await page.screenshot({ path: file.replace(/\.html$/, '.png'), fullPage: true });
    }
  }
  await browser.close();
})();
