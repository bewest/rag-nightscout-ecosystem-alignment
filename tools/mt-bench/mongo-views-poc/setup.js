// Server-enforced tenant scoping and field projection in MongoDB, using a
// read-only view whose pipeline reads $$USER_ROLES, with users granted
// access to the view only.
//
// This is the mechanism §6.1 of the multitenancy discussion did not test.
// Its claim was "MongoDB has no server-enforced per-document ACL comparable
// to RLS"; the question here is whether a view keyed on the connected
// user's roles is one.

const admin = db.getSiblingDB("admin");
admin.createUser({user: "root", pwd: "root", roles: ["root"]});
admin.auth("root", "root");

const ns = db.getSiblingDB("ns");
ns.entries.drop();
ns.entries.insertMany([
  {tenantId: "a", sgv: 101, deviceToken: "SECRET-A-1", device: "Dexcom G7"},
  {tenantId: "a", sgv: 102, deviceToken: "SECRET-A-2", device: "Dexcom G7"},
  {tenantId: "b", sgv: 201, deviceToken: "SECRET-B-1", device: "loop://iPhone"},
  {tenantId: "b", sgv: 202, deviceToken: "SECRET-B-2", device: "loop://iPhone"},
]);

// One view for every tenant. The pipeline derives the tenant from the roles
// held by whoever is connected, so the view definition is not
// per-tenant — which is the property that makes this comparable to RLS
// rather than to "create one view per customer".
ns.createView("entries_scoped", "entries", [
  {$addFields: {_roles: {
    $map: {input: "$$USER_ROLES", as: "r", in: "$$r.role"}}}},
  {$match: {$expr: {$in: [{$concat: ["tenant_", "$tenantId"]}, "$_roles"]}}},
  // Field-level projection in the same place: the credential never leaves
  // the server for any consumer of this view.
  {$project: {_roles: 0, deviceToken: 0}},
]);

// A second view at a stricter disclosure level, to test whether projection
// profiles can be expressed as views.
ns.createView("entries_effect_only", "entries", [
  {$addFields: {_roles: {
    $map: {input: "$$USER_ROLES", as: "r", in: "$$r.role"}}}},
  {$match: {$expr: {$in: [{$concat: ["tenant_", "$tenantId"]}, "$_roles"]}}},
  {$project: {_id: 0, sgv: 1}},
]);

admin.createRole({role: "tenant_a", privileges: [], roles: []});
admin.createRole({role: "tenant_b", privileges: [], roles: []});

// Read on the VIEWS only. No privilege on ns.entries at all.
admin.createRole({
  role: "view_reader",
  privileges: [
    {resource: {db: "ns", collection: "entries_scoped"}, actions: ["find"]},
    {resource: {db: "ns", collection: "entries_effect_only"}, actions: ["find"]},
  ],
  roles: [],
});

admin.createUser({user: "alice", pwd: "pw", roles: [
  {role: "view_reader", db: "admin"}, {role: "tenant_a", db: "admin"}]});
admin.createUser({user: "bob", pwd: "pw", roles: [
  {role: "view_reader", db: "admin"}, {role: "tenant_b", db: "admin"}]});
// Holds the view privilege but no tenant role at all.
admin.createUser({user: "nobody", pwd: "pw", roles: [
  {role: "view_reader", db: "admin"}]});

print("setup ok: " + ns.entries.countDocuments() + " base rows");
