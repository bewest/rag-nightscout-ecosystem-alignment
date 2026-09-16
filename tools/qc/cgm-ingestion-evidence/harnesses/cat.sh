#!/bin/bash
# categorise a numstat diff into the release-readiness §3 buckets
awk -F'\t' '
function bucket(p) {
  if (p ~ /^tests\//) return "Tests";
  if (p ~ /^docs\//) return "Evidence docs";
  if (p == "package-lock.json" || p ~ /package-lock\.json$/) return "Lockfile";
  if (p ~ /^tools\//) return "Tooling";
  if (p ~ /^\.github\/workflows\//) return "CI workflows";
  if (p ~ /^(lib|views|bin|webpack|static)\//) return "Production";
  if (p ~ /^(server\.js|app\.js)$/) return "Production";
  return "Other";
}
{
  p=$3;
  # handle rename syntax a => b
  if (p ~ / => /) { sub(/.*=> /,"",p); gsub(/[{}]/,"",p); }
  b=bucket(p);
  f[b]++;
  ins[b]+= ($1=="-"?0:$1);
  del[b]+= ($2=="-"?0:$2);
  tf++; ti+= ($1=="-"?0:$1); td+= ($2=="-"?0:$2);
}
END {
  order="Production Tests Evidence-docs Lockfile Tooling CI-workflows Other";
  n=split(order,o," ");
  for(i=1;i<=n;i++){ k=o[i]; gsub(/-/," ",k); if(f[k]) printf "  %-16s %4d files  +%-7d -%-7d\n", k, f[k], ins[k], del[k]; }
  printf "  %-16s %4d files  +%-7d -%-7d\n", "TOTAL", tf, ti, td;
}'
