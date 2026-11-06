'use strict';
// Read-only client provenance check. Compile the selected Git source in scratch,
// then compare every emitted runtime JS file with the client that would execute.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function runtimeFiles (root, prefix = '') {
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true }).flatMap(entry => {
    const relative = path.join(prefix, entry.name);
    return entry.isDirectory() ? runtimeFiles(path.join(root, entry.name), relative) : entry.name.endsWith('.js') ? [relative] : [];
  }).sort();
}
module.exports = function verifyBuild (checkout) {
  let scratch;
  try {
    const git = args => execFileSync('git', ['-C', checkout, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, GIT_OPTIONAL_LOCKS: '0' } }).trim();
    const head = git(['rev-parse', '--verify', 'HEAD^{commit}']);
    const sources = ['src', 'package.json', 'package-lock.json', 'tsconfig.json', 'tsconfig-build.json'];
    git(['diff', '--quiet', 'HEAD', '--', ...sources]);
    scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'm4-client-source-'));
    const archive = execFileSync('git', ['-C', checkout, 'archive', '--format=tar', head, ...sources], { maxBuffer: 128 * 1024 * 1024 });
    execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
    fs.symlinkSync(path.join(checkout, 'node_modules'), path.join(scratch, 'node_modules'), 'dir');
    const compiler = path.join(checkout, 'node_modules/typescript');
    const version = JSON.parse(fs.readFileSync(path.join(compiler, 'package.json'))).version;
    const lock = JSON.parse(fs.readFileSync(path.join(scratch, 'package-lock.json')));
    if (lock.packages?.['node_modules/typescript']?.version !== version) throw new Error('TypeScript version differs from selected client lock');
    execFileSync(process.execPath, [path.join(compiler, 'bin/tsc'), '-p', path.join(scratch, 'tsconfig-build.json')],
      { cwd: scratch, stdio: ['ignore', 'pipe', 'pipe'], timeout: 60000 });
    const expected = runtimeFiles(path.join(scratch, 'dist'));
    const actual = runtimeFiles(path.join(checkout, 'dist'));
    if (!expected.length) throw new Error('Source build emitted no runtime files');
    const files = [...new Set([...expected, ...actual])].sort().map(file => {
      const built = path.join(scratch, 'dist', file), installed = path.join(checkout, 'dist', file);
      const sourceHash = fs.existsSync(built) ? digest(fs.readFileSync(built)) : null;
      const installedHash = fs.existsSync(installed) ? digest(fs.readFileSync(installed)) : null;
      return { file, source_sha256: sourceHash, installed_sha256: installedHash, equal: sourceHash !== null && sourceHash === installedHash };
    });
    return { ok: files.every(file => file.equal), head, typescript: version, runtime_files: files.length, files,
      mismatches: files.filter(file => !file.equal).map(file => file.file) };
  } catch (error) {
    return { ok: false, error: error.message };
  } finally {
    if (scratch) fs.rmSync(scratch, { recursive: true, force: true });
  }
};
