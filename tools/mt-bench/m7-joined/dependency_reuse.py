"""Opt-in no-install owned dependency copies; no adapter policy or actor launch.

The caller supplies exact source package/lock bytes from its already checked git
head and an explicitly selected qualified receipt hash. Preflight has no writes.
The returned provenance supplements, never replaces, adapter source/image checks.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

MODULES = ('socket.io-client', 'pg', 'js-yaml')


def need(ok, code):
    if not ok:
        raise RuntimeError('M7_DEPENDENCY_REUSE_' + code)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def tree(root):
    """Hash every file and internal relative link; reject special/escaping entries."""
    root = Path(root)
    need(root.is_dir() and not root.is_symlink(), 'TREE_ROOT')
    root = root.resolve()
    rows = []
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            p = Path(parent) / name
            mode = p.lstat().st_mode
            relative = p.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                target = os.readlink(p)
                need(not os.path.isabs(target) and p.exists() and p.resolve().is_relative_to(root), 'LINK_ESCAPE')
                rows.append([relative, 'link', target])
            elif stat.S_ISREG(mode):
                rows.append([relative, 'file', mode & 0o111, p.stat().st_size, file_sha(p)])
            elif stat.S_ISDIR(mode):
                rows.append([relative, 'directory'])
            else:
                need(False, 'SPECIAL_FILE')
    rows.sort()
    return {'sha256': sha(json.dumps(rows, separators=(',', ':')).encode()),
            'entries': len(rows), 'files': sum(row[1] == 'file' for row in rows)}


OBSERVE = r"""
const fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module'),crypto=require('node:crypto');
if(process.env.NODE_OPTIONS||process.env.NODE_PATH||process.env.LD_PRELOAD)throw Error('PRELOAD');
const root=fs.realpathSync(process.argv[1]),r=createRequire(path.join(root,'package.json'));
const lock=JSON.parse(fs.readFileSync(path.join(root,'package-lock.json'))),modules={};
for(const name of ['socket.io-client','pg','js-yaml']){
 const entry=fs.realpathSync(r.resolve(name)),version=r(name+'/package.json').version,value=r(name);
 if(!entry.startsWith(root+path.sep+'node_modules'+path.sep)||lock.packages?.['node_modules/'+name]?.version!==version)throw Error('CONTEXT');
 if(name==='pg'?(typeof value.Pool!=='function'||typeof value.Client!=='function'):name==='js-yaml'?typeof value.load!=='function':typeof value.io!=='function')throw Error('EXPORT');
 modules[name]={relativeEntry:path.relative(root,entry),version,entrySha256:crypto.createHash('sha256').update(fs.readFileSync(entry)).digest('hex')};
}
const h=process.report.getReport().header;
console.log(JSON.stringify({platform:{os:process.platform,arch:process.arch,nodeABI:process.versions.modules,glibc:h.glibcVersionRuntime||null},modules}));
"""


def observe(root, tools, run):
    """run(argv) is the caller's clean, bounded command adapter; no npm install."""
    for name in ('node', 'npm'):
        tool = tools[name]
        need(Path(tool['path']).is_file() and file_sha(tool['path']) == tool['sha256'], 'TOOL_HASH')
        # Invoke npm's JS entry with the exact selected Node, not its env shebang.
        argv = [tools['node']['path'], '--max-old-space-size=128']
        argv += ['--version'] if name == 'node' else [tool['path'], '--version']
        need(run(argv).strip() == tool['version'], 'TOOL_VERSION')
    value = json.loads(run([tools['node']['path'], '--max-old-space-size=128', '-e', OBSERVE, str(root)]))
    need(set(value) == {'platform', 'modules'} and set(value['modules']) == set(MODULES), 'OBSERVATION')
    return value


def preflight(*, source, receipt_path, receipt_sha256, package_bytes, lock_bytes, tools, run,
              source_preparation=None):
    """Read-only qualification; errors must occur before caller creates a target."""
    source = Path(source)
    need(source.is_dir() and not source.is_symlink(), 'SOURCE_ROOT')
    source = source.resolve()
    receipt_path = Path(receipt_path)
    need(receipt_path.is_file() and not receipt_path.is_symlink() and file_sha(receipt_path) == receipt_sha256, 'RECEIPT_HASH')
    receipt = json.loads(receipt_path.read_text())
    need(receipt.get('kind') == 'owned-lockfile-install', 'QUALIFICATION_KIND')
    need(receipt.get('tools') == tools, 'TOOL_PROVENANCE')
    for name, key, content in [('package.json', 'packageSha256', package_bytes), ('package-lock.json', 'lockSha256', lock_bytes)]:
        need(type(content) is bytes and receipt.get(key) == sha(content) and (source / name).is_file()
             and not (source / name).is_symlink() and (source / name).read_bytes() == content, 'SOURCE_FINGERPRINT')
    context = receipt.get('contexts', {}).get('generator', {})
    origin = Path(context.get('root', ''))
    need(origin.is_absolute() and context.get('dependencyRoot') == str(origin / 'node_modules')
         and context.get('nodeBinary') == tools['node']['path'] and context.get('nodeVersion') == tools['node']['version'], 'QUALIFIED_ROOT')
    if source_preparation is None:
        need(source == origin, 'QUALIFIED_ROOT')
    else:
        # Explicit alternate retained source, never implicit nearest-tree search.
        path = Path(source_preparation['path'])
        need(path.is_file() and not path.is_symlink()
             and file_sha(path) == source_preparation['sha256'], 'SOURCE_RECEIPT_HASH')
        prepared = json.loads(path.read_text())
        need(prepared.get('status') == 'OWN_SOURCE_DEPENDENCY_AND_POSTINSTALL_PREPARATION_PASS_NO_NATIVE'
             and prepared.get('sourceTree') == str(source)
             and prepared.get('sourceHead') == source_preparation['head']
             and prepared.get('packageSha256') == sha(package_bytes)
             and prepared.get('lockSha256') == sha(lock_bytes)
             and prepared.get('realCopiedDependencyTree') is True
             and prepared.get('nestedRootNodeModulesAbsent') is True
             and prepared.get('absoluteLinks') == [] and prepared.get('brokenLinks') == []
             and prepared.get('postinstall', {}).get('exit') == 0
             and prepared['postinstall'].get('command') == [tools['node']['path'], 'bin/postinstall.js']
             and file_sha(source / 'node_modules/.package-lock.json') == prepared.get('dependencyInstalledLockSha256'), 'SOURCE_PREPARATION')
    # Verify the entire selected installed lock inventory, allowing only explicitly
    # optional packages omitted by the original qualified --omit=optional install.
    lock = json.loads(lock_bytes)
    need(isinstance(lock.get('packages'), dict) and lock['packages'], 'LOCK_FORMAT')
    for relative, expected in lock['packages'].items():
        if not relative:
            continue
        need(relative.startswith('node_modules/') and '..' not in Path(relative).parts, 'LOCK_PATH')
        package = source / relative / 'package.json'
        if not package.exists() and expected.get('optional') is True:
            continue
        need(package.is_file() and not package.is_symlink(), 'INCOMPLETE')
        need(json.loads(package.read_text()).get('version') == expected.get('version'), 'PACKAGE_VERSION')
    for name in MODULES:
        original_entry = Path(context.get('modules', {}).get(name, {}).get('entry', ''))
        need(original_entry.is_relative_to(origin / 'node_modules'), 'MODULE_PROVENANCE')
        entry = source / original_entry.relative_to(origin)
        need(entry.is_file() and entry.resolve().is_relative_to(source / 'node_modules')
             and file_sha(entry) == context['modules'][name].get('entrySha256'), 'MODULE_FINGERPRINT')
    before = tree(source / 'node_modules')
    actual = observe(source, tools, run)
    for name in MODULES:
        old = context.get('modules', {}).get(name, {})
        new = actual['modules'][name]
        need(old.get('entry') == str(origin / new['relativeEntry']) and old.get('version') == new['version']
             and old.get('entrySha256') == new['entrySha256'], 'MODULE_PROVENANCE')
    need(tree(source / 'node_modules') == before, 'SOURCE_CHANGED')
    return {'version': 1, 'source': str(source), 'receipt': str(receipt_path.resolve()), 'receiptSha256': receipt_sha256,
            'packageSha256': sha(package_bytes), 'lockSha256': sha(lock_bytes), 'tools': tools,
            'tree': before, 'sourcePreparation': source_preparation, **actual}


def copy_owned(*, destination, qualification, package_bytes, lock_bytes, run):
    """Create a new owned copy after read-only qualification; never link a peer tree.

    A failed copy is retained at the new destination with no ready marker. Callers
    must not run or adopt it. No existing destination is removed or overwritten.
    """
    destination = Path(destination)
    q = qualification
    source = Path(q['source'])
    need(not destination.exists() and not destination.is_symlink(), 'TARGET_EXISTS')
    need(destination.parent.is_dir() and not destination.parent.is_symlink(), 'TARGET_PARENT')
    need(not destination.resolve().is_relative_to(source), 'TARGET_WITHIN_SOURCE')
    need(sha(package_bytes) == q['packageSha256'] and sha(lock_bytes) == q['lockSha256'], 'INPUT_CHANGED')
    # Revalidate the selected provenance, tools/platform/modules and complete tree
    # before the first target write; never trust a stale preflight object alone.
    fresh = preflight(source=source, receipt_path=q['receipt'], receipt_sha256=q['receiptSha256'],
                      package_bytes=package_bytes, lock_bytes=lock_bytes, tools=q['tools'], run=run,
                      source_preparation=q['sourcePreparation'])
    need(fresh == q, 'QUALIFICATION_CHANGED')
    destination.mkdir(mode=0o700)
    (destination / 'package.json').write_bytes(package_bytes)
    (destination / 'package-lock.json').write_bytes(lock_bytes)
    shutil.copytree(source / 'node_modules', destination / 'node_modules', symlinks=True)
    need(tree(destination / 'node_modules') == q['tree'] and tree(source / 'node_modules') == q['tree'], 'COPY_CHANGED')
    need(observe(destination, q['tools'], run) == {'platform': q['platform'], 'modules': q['modules']}, 'COPIED_CONTEXT')
    need(tree(destination / 'node_modules') == q['tree'], 'COPY_CHANGED')
    provenance = {'kind': 'owned-qualified-dependency-copy', 'qualification': q,
                  'packageSha256': q['packageSha256'], 'lockSha256': q['lockSha256'],
                  'tools': q['tools'], 'installFlags': [], 'network': 'NOT_USED'}
    (destination / 'dependency-reuse-ready.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return provenance
