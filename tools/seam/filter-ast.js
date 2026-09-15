// The storage seam's filter language, with one adapter per backend.
//
// WHY THIS SHAPE. API v3 already has an AST: `filterDef` is an array of
// {field, operator, value} with a top-level logicalOperator, and
// lib/api3/storage/mongoCollection/utils.js parseFilter() is already its MongoDB
// adapter. So this is not a new design — it is v3's existing filter model with the
// smallest set of extensions that let API v1's real output be expressed in it,
// plus a second adapter.
//
// The extensions, each because a measured v1 shape needs it (see COVERAGE below):
//
//   1. NESTED GROUPS. v3's AST is flat: every clause is joined by one
//      logicalOperator. v1 emits top-level $or with clause objects, so a group
//      node is required. This is the only structural change.
//   2. `exists`. v1 passes $exists through; it is not one of v3's nine. Added
//      deliberately rather than by accident, because the alternative is that
//      v1 queries using it stop working.
//
// Everything else v1 produces maps onto v3's nine operators unchanged:
// implicit equality -> eq; {$gte, $lte} on one field -> two clauses; dotted paths
// -> field names that happen to contain dots.
//
// WHAT THE AST DELIBERATELY CANNOT EXPRESS is the point of it. There is no
// $where, no $expr, no arbitrary pipeline, no operator escape hatch. An AST that
// cannot represent an unlisted operator IS the allowlist that {M} §6.5 says does
// not exist today, so the security fix is structural rather than a check someone
// has to remember to write.
//
// NODE SHAPES
//   {op: 'and'|'or', nodes: [...]}                      group
//   {op: <cmp>, field: 'a.b', value: v}                  comparison
//   cmp: eq ne gt gte lt lte in nin re exists
//
// `in`/`nin` take an array. `re` takes a pattern string; both adapters bound it
// (see RE_MAX_LEN) because an unbounded regex is the live ReDoS vector.

'use strict';

const CMP = new Set(['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'nin', 're', 'exists']);
const GROUP = new Set(['and', 'or']);
const RE_MAX_LEN = 128;

// ---------------------------------------------------------------- validation
//
// Structural validation is the allowlist. It runs before either adapter, so a
// malformed or unlisted operator can never reach a backend.

function validate (node, path = '$') {
  if (!node || typeof node !== 'object' || Array.isArray(node)) {
    throw new TypeError(`${path}: filter node must be an object`);
  }
  const { op } = node;
  if (GROUP.has(op)) {
    if (!Array.isArray(node.nodes)) throw new TypeError(`${path}: ${op} requires nodes[]`);
    node.nodes.forEach((n, i) => validate(n, `${path}.${op}[${i}]`));
    return node;
  }
  if (!CMP.has(op)) {
    throw new TypeError(`${path}: unsupported operator '${op}' ` +
      `(allowed: ${[...CMP].join(' ')})`);
  }
  if (typeof node.field !== 'string' || !node.field.length) {
    throw new TypeError(`${path}: ${op} requires a field name`);
  }
  // A field name is a dotted path of plain segments. This also keeps SQL
  // identifier construction safe by construction rather than by escaping.
  if (!/^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(node.field)) {
    throw new TypeError(`${path}: invalid field path '${node.field}'`);
  }
  if (op === 'in' || op === 'nin') {
    if (!Array.isArray(node.value)) throw new TypeError(`${path}: ${op} requires an array`);
  }
  if (op === 're') {
    if (typeof node.value !== 'string') throw new TypeError(`${path}: re requires a string`);
    if (node.value.length > RE_MAX_LEN) {
      throw new TypeError(`${path}: re pattern exceeds ${RE_MAX_LEN} characters`);
    }
  }
  if (op === 'exists' && typeof node.value !== 'boolean') {
    throw new TypeError(`${path}: exists requires a boolean`);
  }
  return node;
}

// ---------------------------------------------------------------- MongoDB
//
// Mirrors parseFilter()'s operator mapping so behaviour is unchanged for v3, and
// adds grouping. Each comparison becomes its own single-key clause rather than
// being merged onto a shared field key: {$and: [{a:{$gte:1}}, {a:{$lte:9}}]}
// rather than {a:{$gte:1,$lte:9}}. Both match identically in MongoDB, and the
// un-merged form is what keeps the translation total — merging would have to
// special-case a field appearing under both `and` and `or`.

const MONGO_OP = { eq: '$eq', ne: '$ne', gt: '$gt', gte: '$gte', lt: '$lt', lte: '$lte',
  in: '$in', nin: '$nin' };

function toMongo (node) {
  validate(node);
  return build(node);

  function build (n) {
    if (GROUP.has(n.op)) {
      if (n.nodes.length === 0) return {};
      return { [n.op === 'and' ? '$and' : '$or']: n.nodes.map(build) };
    }
    if (n.op === 're') return { [n.field]: { $regex: n.value } };
    if (n.op === 'exists') return { [n.field]: { $exists: n.value } };
    return { [n.field]: { [MONGO_OP[n.op]]: n.value } };
  }
}

// ---------------------------------------------------------------- PostgreSQL
//
// Emits a parameterised fragment against the §6.3 storage shape: indexed fields
// are generated columns, everything else lives in a `doc` jsonb column. The
// column set is passed in, so the same AST produces a column comparison where one
// exists and a jsonb path traversal where it does not — which is the whole point
// of generated columns, and is invisible to the caller.
//
// Values are ALWAYS parameters ($1, $2, ...). Field paths are validated
// identifiers (see validate()), never interpolated user input.

const SQL_OP = { eq: '=', ne: '<>', gt: '>', gte: '>=', lt: '<', lte: '<=' };

function toSql (node, opts = {}) {
  validate(node);
  const columns = new Set(opts.columns || []);   // generated columns available
  const jsonbCol = opts.jsonbColumn || 'doc';
  const params = [];

  const text = build(node);
  return { text, params };

  function ref (field, wantText) {
    if (columns.has(field)) return `"${field}"`;
    // jsonb path: a.b.c -> doc#>>'{a,b,c}' (text) or doc#>'{a,b,c}' (jsonb)
    const path = '{' + field.split('.').join(',') + '}';
    return `${jsonbCol}#${wantText ? '>>' : '>'}'${path}'`;
  }

  function param (v) { params.push(v); return `$${params.length}`; }

  // jsonb extraction yields text, so a numeric comparison has to cast. Casting
  // the EXTRACTED value (not the literal) is what keeps `sgv >= 100` from
  // becoming a string comparison — the same class of bug the v1 walker has when
  // it leaves a value as a string.
  function cmp (n) {
    const isCol = columns.has(n.field);
    const numeric = typeof n.value === 'number';
    if (isCol) return { lhs: `"${n.field}"`, rhs: param(n.value) };
    if (numeric) return { lhs: `(${ref(n.field, true)})::numeric`, rhs: param(n.value) };
    if (typeof n.value === 'boolean') return { lhs: `(${ref(n.field, true)})::boolean`, rhs: param(n.value) };
    return { lhs: ref(n.field, true), rhs: param(n.value) };
  }

  function build (n) {
    if (GROUP.has(n.op)) {
      if (n.nodes.length === 0) return 'TRUE';
      return '(' + n.nodes.map(build).join(n.op === 'and' ? ' AND ' : ' OR ') + ')';
    }
    if (n.op === 'exists') {
      // ALWAYS reads the document, never a generated column, even when one
      // exists for this field. MongoDB's $exists is about KEY PRESENCE, and a
      // generated column is built with ->> which returns SQL NULL for both an
      // absent key and an explicit JSON null — so it cannot tell them apart.
      // `doc #> '{path}'` can: it yields jsonb 'null' for the first and SQL NULL
      // for the second. Verified, and it was the only remaining source of
      // disagreement once `nin` was fixed.
      const present = `${jsonbCol} #> '{${n.field.split('.').join(',')}}' IS NOT NULL`;
      return n.value ? present : `NOT (${present})`;
    }
    if (n.op === 're') {
      // ~ is POSIX regex. Mongo's $regex is PCRE-ish; the differential test in
      // validate.js reports where they disagree rather than pretending they do
      // not. Patterns are length-bounded by validate().
      return `(${ref(n.field, true)}) ~ ${param(n.value)}`;
    }
    if (n.op === 'in' || n.op === 'nin') {
      if (n.value.length === 0) return n.op === 'in' ? 'FALSE' : 'TRUE';
      const numeric = n.value.every(v => typeof v === 'number');
      const lhs = columns.has(n.field) ? `"${n.field}"`
        : numeric ? `(${ref(n.field, true)})::numeric` : ref(n.field, true);
      const list = n.value.map(param).join(', ');
      if (n.op === 'in') return `${lhs} IN (${list})`;
      // $nin matches a MISSING field in MongoDB (absent is not among the listed
      // values), but `NULL NOT IN (...)` is NULL in SQL and therefore does not
      // match. Same three-valued-logic gap as `ne`, and it was the single
      // largest source of disagreement in the first validate.js run.
      return `(${lhs} IS NULL OR ${lhs} NOT IN (${list}))`;
    }
    const { lhs, rhs } = cmp(n);
    // SQL three-valued logic: `x <> 1` is NULL (not true) when x is absent, while
    // Mongo's $ne matches missing fields. Made explicit so the two agree.
    if (n.op === 'ne') return `(${lhs} IS DISTINCT FROM ${rhs})`;
    return `${lhs} ${SQL_OP[n.op]} ${rhs}`;
  }
}

// ---------------------------------------------------------------- helpers

const and = (...nodes) => ({ op: 'and', nodes });
const or = (...nodes) => ({ op: 'or', nodes });
const cmp = (op, field, value) => ({ op, field, value });

module.exports = { validate, toMongo, toSql, and, or, cmp, CMP, GROUP, RE_MAX_LEN };
