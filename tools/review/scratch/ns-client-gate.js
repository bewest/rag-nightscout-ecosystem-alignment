// Client-render gate: fails when the Nightscout chart does not draw real data.
const { chromium } = require('playwright-core');
const URL_ = process.argv[2];
const MIN_POINTS = parseInt(process.argv[3] || '50', 10);
(async () => {
  const b = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  const p = await b.newPage();
  const errors = [];
  p.on('pageerror', e => errors.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  let verdict = {};
  try {
    await p.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await p.waitForFunction(
      n => document.querySelectorAll('#chartContainer circle').length >= n,
      MIN_POINTS, { timeout: 45000 });
    verdict.points = await p.$$eval('#chartContainer circle', e => e.length);
    verdict.currentBG = (await p.textContent('#currentBG').catch(() => null) || '').trim();
    verdict.serverFailedBanner = await p.locator('text=Nightscout server failed').count();
    verdict.ok = verdict.points >= MIN_POINTS
              && /^\d+(\.\d+)?$/.test(verdict.currentBG)
              && verdict.serverFailedBanner === 0;
  } catch (e) {
    verdict.ok = false; verdict.error = e.message.split('\n')[0];
    verdict.points = await p.$$eval('#chartContainer circle', e => e.length).catch(() => -1);
    verdict.currentBG = (await p.textContent('#currentBG').catch(() => null) || '').trim();
  }
  verdict.jsErrors = errors.slice(0, 3);
  await b.close();
  console.log(JSON.stringify(verdict, null, 1));
  process.exit(verdict.ok ? 0 : 1);
})();
