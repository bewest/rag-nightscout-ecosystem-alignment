#!/usr/bin/env bash
# Image = git archive of core 0392acf9 with deploy/multitenant replaced by nightscout-deploy's
# bindings/compose/multitenant at the deploy commit; revision label = core commit.
set -euo pipefail
# Used for the 0392acf9 runs only. From deploy d1c7aca+ the deploy repository's overlay path
# (tools/compose-overlay.sh, or the .overlay.json marker by hand, then prepare.js + build.js) builds and
# labels the image from both commits; the later runs used that.
C=${CAP_BUILD_CORE:?core checkout containing commit 0392acf9}
D=${CAP_DEPLOY:?nightscout-deploy checkout at the deploy commit}
core=0392acf97c720a7e121eea47a9d42a0c8dbe9e73; dep=$(git -C $D rev-parse HEAD)
tag=nscap:0392acf9-${dep:0:7}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir $tmp/ctx; git -C $C archive $core | tar -x -C $tmp/ctx
rm -rf $tmp/ctx/deploy/multitenant; mkdir $tmp/ctx/deploy/multitenant
git -C $D archive HEAD:bindings/compose/multitenant | tar -x -C $tmp/ctx/deploy/multitenant
cd $tmp/ctx && docker build --pull=false --build-arg NS_SOURCE_COMMIT=$core --label org.opencontainers.image.revision=$core \
  --label org.nightscout.deploy.revision=$dep -t $tag -f deploy/multitenant/Dockerfile .
echo "built $tag"
