#!/usr/bin/env bash
#
# empty-root-control.sh — the standing NEGATIVE CONTROL for a gate that reads
# files (documents, package.json, a checkout) to reach its verdict.
#
#   empty-root-control.sh <gate.js> [args...]
#
# It runs the gate with QUEUE_GATE_ROOT pointed at an EMPTY directory, so every
# input the gate depends on is absent, and exits 0 only if the gate did NOT
# pass. A gate that still exits 0 with none of its inputs present is not
# reading anything: that is the P0-E failure — `git log ... | grep -q .` passed
# against origin/dev, origin/master and bf/alarms alike.
#
# This control is DELIBERATELY WEAK, and it is worth being honest about which
# question it answers. It shows a gate is coupled to its inputs at all. It does
# NOT show the gate is coupled to the right PROPERTY of those inputs — for that
# a gate needs a property-specific control, which is what `ablate.sh`,
# `--rev`-mode gates and the hand-written controls in queue/gate-controls.yaml
# provide. Use this one where nothing sharper exists, and say so in `proves`.
#
# IT EXITS WITH THE GATE'S OWN STATUS, because that is what the control
# convention in queue/gate-controls.yaml requires: a control IS the gate
# applied to a known-negative, and it must exit NON-ZERO. A wrapper that
# inverted the status here would be one more place for a sign error to hide,
# and a sign error in a vacuity checker is the funniest possible bug.
# CONTROL-INVALID on stdout means the control could not be set up at all.
set -u

if [ "$#" -lt 1 ]; then
  echo "CONTROL-INVALID: usage: empty-root-control.sh <gate.js> [args...]"
  exit 90
fi

GATE="$1"; shift
[ -f "$GATE" ] || { echo "CONTROL-INVALID: no such gate script: $GATE"; exit 90; }

EMPTY="$(mktemp -d "${TMPDIR:-/tmp}/queue-empty-root-XXXXXX")"
trap 'rm -rf "$EMPTY"' EXIT

out="$(QUEUE_GATE_ROOT="$EMPTY" node "$GATE" "$@" 2>&1)"
rc=$?
echo "$out" | tail -6
echo "gate exited $rc with QUEUE_GATE_ROOT=<empty dir>"
[ "$rc" -eq 0 ] && echo "the gate passed with none of its inputs present"
exit "$rc"
