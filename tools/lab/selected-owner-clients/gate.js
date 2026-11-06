'use strict';
// Standalone preparation instrument: NEVER a registered queue/default gate.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
async function main (argv) {
  const options = {};
  for (let i = 0; i < argv.length; i += 2) {
    assert.ok(['--repo', '--dependencies', '--out', '--ref', '--control'].includes(argv[i]), 'unknown argument');
    assert.ok(argv[i + 1], 'missing argument'); assert.ok(!options[argv[i]], 'duplicate argument'); options[argv[i]] = argv[i + 1];
  }
  const { run, HEAD } = require('./runner');
  assert.equal(options['--ref'], HEAD, 'preparation supports frozen reviewed source only');
  assert.ok(!options['--control'] || options['--control'] === 'intersection', 'only archived intersection ablation is defined');
  for (const name of ['--repo', '--dependencies', '--out']) assert.ok(path.isAbsolute(options[name]), name + ' must be absolute');
  assert.equal(execFileSync('git', ['-C', options['--repo'], 'rev-parse', options['--ref'] + '^{commit}'], { encoding: 'utf8' }).trim(), HEAD);
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-selected-owner-'));
  try {
    const tar = execFileSync('git', ['-C', options['--repo'], 'archive', HEAD], { maxBuffer: 256 * 1024 * 1024 });
    execFileSync('tar', ['-xf', '-', '-C', scratch], { input: tar });
    const dependencies = options['--dependencies'];
    assert.ok(fs.readFileSync(path.join(scratch, 'package-lock.json')).equals(fs.readFileSync(path.join(path.dirname(dependencies), 'package-lock.json'))), 'matching private dependency lock required');
    fs.symlinkSync(dependencies, path.join(scratch, 'node_modules'));
    const result = await run({ worktree: scratch, out: options['--out'], control: options['--control'] === 'intersection' });
    console.log(JSON.stringify({ ok: result.ok, failure: result.failure, head: result.head, control: result.control }));
    return result.ok ? 0 : 1;
  } finally { fs.rmSync(scratch, { recursive: true, force: true }); }
}
if (require.main === module) main(process.argv.slice(2)).then(code => { process.exitCode = code; }, error => { console.error(error.message); process.exitCode = 2; });
module.exports = { main };
