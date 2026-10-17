// Contact sheet per diagram: every candidate side by side, as HTML and PNG.
//   node sheet.js <build dir> <chrome> <out dir> [variant ...]
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const [BUILD, CHROME, OUT, ...pick] = process.argv.slice(2);
const VARIANTS = pick.length ? pick : ['dot-spline', 'grid', 'grid-z', 'neato-ortho', 'elk', 'avoid', 'control-grid', 'control-random'];
const COLS = VARIANTS.length <= 2 ? VARIANTS.length : 3;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: COLS * 640, height: 1000 } });
  const suffix = pick.length ? '-' + pick.join('-vs-') : '';
  for (const dia of fs.readdirSync(BUILD).filter((d) => fs.statSync(path.join(BUILD, d)).isDirectory()).sort()) {
    const cells = VARIANTS.map((v) => {
      const f = path.join(BUILD, dia, v + '.svg');
      const body = fs.existsSync(f) ? fs.readFileSync(f, 'utf8').replace(/<\?xml[^>]*>/, '').replace(/<!DOCTYPE[^>]*>/, '') : '<p>no render</p>';
      return `<figure><figcaption>${v}</figcaption><div class="c">${body}</div></figure>`;
    }).join('\n');
    const html = `<!doctype html><meta charset="utf-8"><title>${dia}</title><style>
      body{font:14px Helvetica,sans-serif;margin:12px;background:#fff}
      .g{display:grid;grid-template-columns:repeat(${COLS},1fr);gap:14px}
      figure{margin:0;border:1px solid #ccc;padding:6px}
      figcaption{font-weight:bold;margin-bottom:4px}
      .c svg{max-width:100%;height:auto;max-height:${pick.length ? 1400 : 760}px}
      </style><h2>${dia}</h2><div class="g">${cells}</div>`;
    const file = path.join(OUT, `${dia}${suffix}.html`);
    fs.writeFileSync(file, html);
    await page.goto('file://' + path.resolve(file));
    await page.waitForTimeout(200);
    await page.screenshot({ path: file.replace(/\.html$/, '.png'), fullPage: true });
  }
  await browser.close();
})();
