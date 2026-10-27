#!/bin/sh
# connector-pin-with-control.sh — RT-CONNECT-PIN-CUTS (BF-65), after the cuts merged.
#
# connector-pin-exposure.js refuses to report when every ref it reads agrees,
# and once every cut merged with the 0.1.0 pin they all did. So the known-bad
# tag v15.0.8 (it pins the v0.0.13 tarball and the 1.16.0 axios override) is
# read beside the refs that must be clean: the gate is met only when every BAD
# line is v15.0.8's and v15.0.8's pin line is BAD.
#
#   usage: connector-pin-with-control.sh <comma-separated refs that must be clean>
refs="${1:-official/dev,official/master}"
out=$(node tools/queue/gates/connector-pin-exposure.js --refs "$refs,v15.0.8"); rc=$?
echo "$out"
if [ "$rc" -eq 1 ] \
   && echo "$out" | grep -q '^  BAD  BF-42/BF-65 v15.0.8: ' \
   && ! echo "$out" | grep '^  BAD ' | grep -vq ' v15.0.8: '; then
  echo "met: only the v15.0.8 control is BAD"
else
  echo "NOT MET: a ref that must be clean is BAD, or the v15.0.8 control did not fail"
  exit 1
fi
