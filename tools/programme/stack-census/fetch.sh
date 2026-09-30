#!/usr/bin/env bash
# Clone (blobless) or fetch every repository in repos.tsv into externals/stack/<owner>__<repo>.
# Blobless clones keep full commit history for the census while fetching file contents only for
# the checked-out default branch.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
dest="$root/externals/stack"
mkdir -p "$dest"
grep -v '^#' "$here/repos.tsv" | while IFS=$'\t' read -r layer repo role; do
  [ -z "$repo" ] && continue
  dir="$dest/${repo/\//__}"
  if [ -d "$dir/.git" ]; then
    git -C "$dir" fetch --quiet --tags origin && git -C "$dir" reset --quiet --hard "origin/HEAD" \
      && echo "fetched $repo" || echo "FAILED fetch $repo"
  else
    git clone --quiet --filter=blob:none "https://github.com/$repo.git" "$dir" \
      && echo "cloned $repo" || echo "FAILED clone $repo"
  fi
done
