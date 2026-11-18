"""Materialize a fresh exact-base population-aware private commissioner.

This copies source and applies one fixed patch. It never renders a case, reads
credentials, runs Docker/Kubernetes, or changes an existing commissioner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
M7 = HERE.parent/'m7-joined'
PATCH = 'commissioning-population-ceiling.patch'
PATCH_SHA256 = 'a7c006c876d593f0fbc6751ad06c6159d5c6e86ef4f08110263c5a897a83396e'
BASE = {
    'ops/staging-k8s/overlay.libsonnet': '10b70e4070a20e551025c7f8226f879e0f67465ccd5e106d28590dc3069aeec4',
    'ops/staging-k8s/bin/preflight.py': '42c1f8c3e6fbd539b166ba82e7fb9eeeb1922cf5221e186429d7ba978513aa68',
    'ops/staging-k8s/bin/frozen.py': '97e7029a4c25c70763104a18071622641d1b9eb3fbaee2782b48b38ac0f5766b',
    'prepare-private-case.py': '5e0a23e4b45f8adbd7d4099215c1df3e8168fe8a840ad05077b9676e8d957c10',
}
RECEIPT_MODULES = {'frozen.py': HERE/'frozen.py', **{
    name: M7/name for name in ('population_ceiling.py', 'primer_options.py',
                              'workload_inputs.py', 'contract.py', 'diagnostic_resources.py')}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(ok, code):
    if not ok:
        raise ValueError('K8S_POPULATION_COMMISSIONER_'+code)


def materialize(source, preparer, out):
    source, preparer = Path(source).resolve(), Path(preparer).resolve()
    requested = Path(out).absolute()
    need(not requested.is_symlink(), 'OUTPUT_EXISTS')
    out = requested.resolve(strict=False)
    patch = HERE/PATCH
    need(sha(patch) == PATCH_SHA256, 'PATCH_CHANGED')
    need(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    need(not out.is_relative_to(source), 'OUTPUT_SCOPE')
    inputs = {name: preparer if name == 'prepare-private-case.py' else source/name for name in BASE}
    need(all(path.is_file() and not path.is_symlink() and sha(path) == BASE[name]
             for name, path in inputs.items()), 'BASE_CHANGED')
    modules = {name: sha(path) for name, path in RECEIPT_MODULES.items()}
    need(b"import population_ceiling" in RECEIPT_MODULES['frozen.py'].read_bytes(), 'HELPER_UNSUPPORTED')
    # The output is an owned new source directory, never a live fixture or case.
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copytree(source/'ops/staging-k8s', out/'ops/staging-k8s',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (out/'ops/bin').mkdir(parents=True)
    shutil.copy2(source/'ops/bin/ro', out/'ops/bin/ro')
    shutil.copy2(preparer, out/'prepare-private-case.py')
    command = ['git', 'apply', str(patch)]
    subprocess.run([*command[:2], '--check', *command[2:]], cwd=out, check=True, capture_output=True)
    subprocess.run(command, cwd=out, check=True, capture_output=True)
    for name, path in RECEIPT_MODULES.items():
        shutil.copy2(path, out/'ops/staging-k8s/bin'/name)
    files = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    receipt = {'version': 1, 'kind': 'population-commissioner-source-v1',
               'base': BASE, 'patchSha256': PATCH_SHA256, 'receiptModules': modules,
               'files': files, 'scope': 'Fresh source copy only; renderer/runtime/capacity UNMEASURED'}
    (out/'population-commissioner.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='exact private phase603 directory containing ops/')
    parser.add_argument('--preparer', type=Path, required=True, help='exact retained prepare-private-case.py')
    parser.add_argument('--out', type=Path, required=True, help='new private source directory')
    args = parser.parse_args()
    print(json.dumps(materialize(args.source, args.preparer, args.out), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
