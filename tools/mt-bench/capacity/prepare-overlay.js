'use strict';
// prepare.js refuses the overlaid tree (BUILD_INPUTS_DIRTY: deploy/multitenant is replaced by
// nightscout-deploy's copy). This wrapper keeps the intent of that check: core HEAD must be the
// pinned commit with no tracked change outside deploy/multitenant, and deploy/multitenant must
// equal nightscout-deploy's bindings/compose/multitenant at the given deploy commit, byte for byte.
//   node prepare-overlay.js <overlay-core-tree> <deploy-checkout> <deploy-commit> --state DIR --port N
const { execFileSync } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const [core, deploy, depCommit, ...rest] = process.argv.slice(2);
const mt = path.join(core, 'deploy/multitenant');
const build = require(path.join(mt, 'build.js'));
const head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: core, encoding: 'utf8' }).trim();
const inputs = ['package.json', 'package-lock.json', '.babelrc', '.browserslistrc', '.dockerignore', 'bundle', 'webpack', 'bin', 'lib', 'static', 'views', 'translations', 'migrations', 'scripts/diagnose-data.js', 'server.js'];
execFileSync('git', ['diff', '--quiet', 'HEAD', '--', ...inputs], { cwd: core });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ovl-'));
try {
  execFileSync('sh', ['-c', `git -C "${deploy}" archive ${depCommit}:bindings/compose/multitenant | tar -x -C "${tmp}"`]);
  execFileSync('diff', ['-r', '-x', '.env', tmp, mt]);
} finally { fs.rmSync(tmp, { recursive: true, force: true }); }
build.assertCleanSource = () => head;
require(path.join(mt, 'prepare.js')).prepare(rest);
console.log('source ' + head + ' deploy ' + depCommit);
