#!/usr/bin/env bash
# Build the campaign controller image from committed sources. Prints the image id; tags it $TAG.
#
#   build.sh TAG                                   harness only (synthetic runner, supervisor, collect tooling)
#   build.sh TAG --template CASE --core DIR@COMMIT --deploy DIR@COMMIT
#                                                  standard runner: also the template case and every input it names
#
# The harness is the alignment commit at HEAD of this checkout (a shallow clone, so kube_adapter.instrument() reads
# the same commit). Core and deploy are shallow fetches of the named commits, placed at the paths the manifest's
# `standard.core` / `standard.binding` name (the checkout paths given here). The template case, its toolsDirectory,
# k6, readonlyGuard, driver node and driver dependencies are copied to the same absolute paths. Two template fields
# are changed in the copy, both for running inside the cluster: the kube context (environment.json and
# native-run-template.json: "in-cluster", the context campaign.py writes into the Pod's kubeconfig) and
# pullSecretCommand (cat of the mounted pull Secret instead of doctl). Pushing the image is a separate,
# maintainer-approved step.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(git -C "$here" rev-parse --show-toplevel)
tag=$1; shift
template= core= deploy=
while [ $# -gt 0 ]; do
  case $1 in
    --template) template=$2; shift 2;;
    --core) core=$2; shift 2;;
    --deploy) deploy=$2; shift 2;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
[ -z "$(git -C "$repo" status --porcelain -- tools/mt-bench)" ] || { echo "tools/mt-bench has uncommitted changes" >&2; exit 2; }
ctx=$(mktemp -d); trap 'rm -rf "$ctx"' EXIT
cp "$here/Dockerfile" "$ctx/"
head=$(git -C "$repo" rev-parse HEAD)
git init -q "$ctx/harness" && git -C "$ctx/harness" fetch -q --depth 1 "file://$repo" "$head" && git -C "$ctx/harness" checkout -q FETCH_HEAD
mkdir -p "$ctx/ws"
shallow() {  # DIR@COMMIT -> same path under ws/
  local dir=${1%@*} commit=${1##*@}
  mkdir -p "$ctx/ws$dir"
  git init -q "$ctx/ws$dir" && git -C "$ctx/ws$dir" fetch -q --depth 1 "file://$dir" "$commit" && git -C "$ctx/ws$dir" checkout -q FETCH_HEAD
}
if [ -n "$template" ]; then
  [ -n "$core" ] && [ -n "$deploy" ] || { echo "--template needs --core and --deploy" >&2; exit 2; }
  shallow "$core"; shallow "$deploy"
  template=$(cd "$template" && pwd)
  python3 - "$template" "$ctx/ws" "$ctx/Dockerfile" <<'PY'
import json, shutil, sys
from pathlib import Path
template, ws = Path(sys.argv[1]), Path(sys.argv[2])
control = json.loads((template/'lifecycle-input.json').read_bytes())
run = json.loads((template/'native-run-template.json').read_bytes())
paths = [template, Path(control['toolsDirectory']), Path(control['k6']), Path(control['readonlyGuard']),
         Path(run['driver']['node']).parent.parent, Path(run['driver']['dependencies'])]
for p in paths:
    target = ws/p.relative_to('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(p, target, symlinks=True) if p.is_dir() else shutil.copy2(p, target)
copy = ws/template.relative_to('/')
for name in ('environment.json', 'native-run-template.json'):
    doc = json.loads((copy/name).read_bytes()); doc['context'] = 'in-cluster'
    (copy/name).write_text(json.dumps(doc, indent=2) + '\n')
control['pullSecretCommand'] = ['cat', '/var/run/campaign-pull/.dockerconfigjson']
(copy/'lifecycle-input.json').write_text(json.dumps(control, indent=2) + '\n')
# render_checks and the probe call `node` by name: the template's node goes first on PATH.
with open(sys.argv[3], 'a') as dockerfile:
    dockerfile.write('ENV PATH=%s:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' % Path(run['driver']['node']).parent)
PY
  cp "$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['toolsDirectory'])" "$template/lifecycle-input.json")/kubectl" "$ctx/kubectl"
else
  cp "$(command -v kubectl)" "$ctx/kubectl"
fi
docker build -q -t "$tag" "$ctx"
