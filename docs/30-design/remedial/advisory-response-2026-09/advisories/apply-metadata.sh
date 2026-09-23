#!/usr/bin/env bash
# apply-metadata.sh — patch the five DRAFT advisories' metadata. Dry run by default.
#
#   ./apply-metadata.sh            show every request that would be sent, send nothing
#   ./apply-metadata.sh --apply    actually send them
#
# This NEVER publishes. `state` is not touched by any call here; publishing a
# draft advisory is a separate, deliberate action in the GitHub UI.
#
# Note on severity vs cvss_vector_string: GitHub derives `severity` from
# `cvss_vector_string` when a CVSS 3.1 vector is supplied. Where a 4.0 vector is
# recommended the API may not accept it in `cvss_vector_string`; those two calls
# set `severity` explicitly and put the 4.0 vector in the body text instead.
set -euo pipefail
REPO=nightscout/cgm-remote-monitor
APPLY=${1:-}

send () {
  local ghsa="$1"; shift
  local payload="$1"; shift
  echo "──────── $ghsa"
  echo "$payload" | python3 -m json.tool
  if [ "$APPLY" = "--apply" ]; then
    echo "$payload" | gh api --method PATCH "/repos/$REPO/security-advisories/$ghsa" --input - >/dev/null \
      && echo "   PATCHED" || echo "   FAILED - check the field names against the current API"
  else
    echo "   (dry run - nothing sent)"
  fi
  echo
}

# 1 ── loadRetro: fix the affected range, add the vector.
send GHSA-gjhc-pc29-r3m6 '{
  "cvss_vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
  "vulnerabilities": [
    { "package": { "ecosystem": "npm", "name": "nightscout" },
      "vulnerable_version_range": ">= 0.9.0",
      "patched_versions": "" } ]
}'

# 2 ── /alarm: ASCII the range operator, add the vector. Range itself is correct.
send GHSA-8849-qjp5-vrrj '{
  "cvss_vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
  "vulnerabilities": [
    { "package": { "ecosystem": "npm", "name": "nightscout" },
      "vulnerable_version_range": ">= 15.0.0",
      "patched_versions": "" } ]
}'

# 3 ── operator injection: the package name does not exist on npm.
send GHSA-r3gv-x7fw-j2v5 '{
  "cvss_vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:L",
  "vulnerabilities": [
    { "package": { "ecosystem": "npm", "name": "nightscout" },
      "vulnerable_version_range": "<= 15.0.8",
      "patched_versions": "" } ]
}'

# 4 ── v3 notes XSS: blank patched field against a closed range.
send GHSA-mjp4-84fw-gj4v '{
  "severity": "high",
  "vulnerabilities": [
    { "package": { "ecosystem": "npm", "name": "nightscout" },
      "vulnerable_version_range": "<= 15.0.7",
      "patched_versions": "15.0.8" } ]
}'

# 5 ── websocket XSS: critical -> high (SC:H/SI:H double-counts the instance).
send GHSA-5mrq-gpqw-q5v5 '{
  "severity": "high",
  "vulnerabilities": [
    { "package": { "ecosystem": "npm", "name": "nightscout" },
      "vulnerable_version_range": "<= 15.0.7",
      "patched_versions": "15.0.8" } ]
}'

cat <<'NOTE'
NOT DONE BY THIS SCRIPT, on purpose:
  - the description/summary rewrites. They are prose and belong in the web UI
    where you can see the rendered result. The XSS advisories' .md files here
    have the exact text; for GHSA-gjhc, GHSA-8849 and GHSA-r3gv it is withheld
    from this public repo until release: `git show ef376ecb:<path>`.
  - publication. Every advisory stays `draft`.
  - credits. Both reporters are already on the advisories as collaborating
    users; confirm the credit type reads the way you want before publishing.
NOTE
