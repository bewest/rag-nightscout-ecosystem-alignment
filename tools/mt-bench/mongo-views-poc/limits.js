// The two things that would change the conclusion: writes, and whether a
// role-keyed view can still use an index on the base collection.
function attempt(label, fn) {
  try { print(`  ${label.padEnd(50)} ${JSON.stringify(fn())}`); }
  catch (e) { print(`  ${label.padEnd(50)} DENIED/ERR: ${String(e.codeName || e.message).slice(0,44)}`); }
}
const ns = db.getSiblingDB("ns");
const adminDb = db.getSiblingDB("admin");

adminDb.auth("root", "root");
// Index the field the view's predicate ultimately selects on.
ns.entries.createIndex({tenantId: 1, sgv: 1});
// Scale it up so a collection scan is distinguishable from an index seek.
const bulk = [];
for (let i = 0; i < 60000; i++) {
  bulk.push({tenantId: i % 2 ? "a" : "b", sgv: 80 + (i % 120),
             deviceToken: "SECRET", device: "Dexcom G7"});
}
ns.entries.insertMany(bulk, {ordered: false});
print(`  base rows: ${ns.entries.countDocuments()}`);
adminDb.logout();

print("\n== writes through the view");
adminDb.auth("alice", "pw");
attempt("insert into the view", () => ns.entries_scoped.insertOne({tenantId: "a", sgv: 99}));
attempt("update through the view", () => ns.entries_scoped.updateOne({sgv: 101}, {$set: {sgv: 1}}).modifiedCount);
attempt("insert into the base collection", () => ns.entries.insertOne({tenantId: "a", sgv: 99}));
adminDb.logout();

print("\n== does the view use the index?");
adminDb.auth("root", "root");
const planView = ns.entries_scoped.find({sgv: {$gte: 150}}).explain("executionStats");
const planBase = ns.entries.find({tenantId: "a", sgv: {$gte: 150}}).explain("executionStats");
function summarise(p) {
  const st = p.executionStats || (p.stages && p.stages[0] && p.stages[0].$cursor &&
    p.stages[0].$cursor.executionStats) || {};
  const winning = JSON.stringify(p.queryPlanner ? p.queryPlanner.winningPlan :
    (p.stages && p.stages[0] && p.stages[0].$cursor && p.stages[0].$cursor.queryPlanner &&
     p.stages[0].$cursor.queryPlanner.winningPlan) || {});
  return {docsExamined: st.totalDocsExamined, keysExamined: st.totalKeysExamined,
          returned: st.nReturned, ms: st.executionTimeMillis,
          scan: winning.indexOf("IXSCAN") >= 0 ? "IXSCAN" : "COLLSCAN"};
}
print("  via role-keyed view: " + JSON.stringify(summarise(planView)));
print("  direct, explicit filter: " + JSON.stringify(summarise(planBase)));
