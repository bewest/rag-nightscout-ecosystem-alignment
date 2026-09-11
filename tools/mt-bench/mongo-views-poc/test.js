// Does a role-keyed read-only view give MongoDB a fail-closed, server-enforced
// equivalent of Postgres RLS — for rows AND for fields?
function attempt(label, fn) {
  try {
    const out = fn();
    print(`  ${label.padEnd(52)} ${JSON.stringify(out)}`);
  } catch (e) {
    print(`  ${label.padEnd(52)} DENIED: ${String(e.codeName || e.message).slice(0, 46)}`);
  }
}

const ns = db.getSiblingDB("ns");
const adminDb = db.getSiblingDB("admin");
// Users live in admin, so authenticate there and then use ns.

print("\n== alice (tenant_a), via the view");
adminDb.auth("alice", "pw");
attempt("view: rows visible", () => ns.entries_scoped.find().toArray().map(d => d.sgv).sort());
attempt("view: any deviceToken leaked?", () =>
  ns.entries_scoped.find({}, {deviceToken: 1}).toArray().some(d => d.deviceToken) ? "YES" : "no");
attempt("base collection: direct read", () => ns.entries.find().toArray().length);
attempt("base collection: aggregate bypass", () =>
  ns.entries.aggregate([{$match: {}}]).toArray().length);
attempt("view: try to re-add the projected-out field", () =>
  ns.entries_scoped.find({}, {deviceToken: 1, sgv: 1}).toArray()
    .some(d => d.deviceToken) ? "LEAKED" : "still absent");
attempt("view: try to query by the projected-out field", () =>
  ns.entries_scoped.find({deviceToken: "SECRET-A-1"}).toArray().length);
attempt("effect-only view: fields returned", () =>
  Object.keys(ns.entries_effect_only.findOne() || {}));
adminDb.logout();

print("\n== bob (tenant_b), same view definition");
adminDb.auth("bob", "pw");
attempt("view: rows visible", () => ns.entries_scoped.find().toArray().map(d => d.sgv).sort());
adminDb.logout();

print("\n== nobody (view privilege, no tenant role)");
adminDb.auth("nobody", "pw");
attempt("view: rows visible", () => ns.entries_scoped.find().toArray().length);
adminDb.logout();

print("\n== root, for contrast");
adminDb.auth("root", "root");
attempt("base collection: direct read", () => ns.entries.find().toArray().length);
attempt("view: rows visible to a user with no tenant role", () =>
  ns.entries_scoped.find().toArray().length);
