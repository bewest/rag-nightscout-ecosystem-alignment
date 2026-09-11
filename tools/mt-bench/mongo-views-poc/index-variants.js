const ns = db.getSiblingDB("ns");
const adminDb = db.getSiblingDB("admin");
adminDb.auth("root", "root");

// Variant: role names ARE the tenant id, so no $concat in the predicate.
ns.createView("entries_plain", "entries", [
  {$match: {$expr: {$in: ["$tenantId",
    {$map: {input: "$$USER_ROLES", as: "r", in: "$$r.role"}}]}}},
  {$project: {deviceToken: 0}},
]);
// Variant: filter first on an indexable equality, then verify by role.
ns.createView("entries_hinted", "entries", [
  {$match: {tenantId: {$in: ["a", "b"]}}},
  {$match: {$expr: {$in: ["$tenantId",
    {$map: {input: "$$USER_ROLES", as: "r", in: "$$r.role"}}]}}},
  {$project: {deviceToken: 0}},
]);

function scan(name, filter) {
  const p = ns[name].find(filter).explain("executionStats");
  const st = p.executionStats || {};
  const s = JSON.stringify(p);
  return {docsExamined: st.totalDocsExamined, keysExamined: st.totalKeysExamined,
          ms: st.executionTimeMillis,
          scan: s.indexOf("IXSCAN") >= 0 ? "IXSCAN" : "COLLSCAN"};
}
print("  entries_plain   " + JSON.stringify(scan("entries_plain", {sgv: {$gte: 150}})));
print("  entries_hinted  " + JSON.stringify(scan("entries_hinted", {sgv: {$gte: 150}})));
print("  base+filter     " + JSON.stringify(scan("entries", {tenantId: "a", sgv: {$gte: 150}})));
