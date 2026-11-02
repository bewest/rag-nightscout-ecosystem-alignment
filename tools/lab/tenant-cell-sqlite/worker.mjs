// Synthetic storage protocol only: these are not Nightscout API endpoints.
class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function requireValue(condition, message) {
  if (!condition) throw new HttpError(400, message);
}

function integer(url, name, fallback, maximum = Number.MAX_SAFE_INTEGER) {
  const raw = url.searchParams.get(name);
  if (raw === null) return fallback;
  requireValue(/^\d+$/.test(raw), `Invalid ${name}`);
  const value = Number(raw);
  requireValue(Number.isSafeInteger(value) && value <= maximum, `Invalid ${name}`);
  return value;
}

function replyError(error) {
  if (error instanceof HttpError) {
    return Response.json({ error: error.message }, { status: error.status });
  }
  console.error("tenant-cell-sqlite handler failed", error);
  return Response.json({ error: "Internal lab error" }, { status: 500 });
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      if (url.pathname === "/health") return Response.json({ lab: true });
      const match = /^\/lab\/([a-z0-9-]+)(\/(?:entries(?:\/[a-z0-9-]+)?|meta))$/.exec(url.pathname);
      if (!match) throw new HttpError(404, "Unknown lab route");
      const [, tenant, path] = match;
      const fixtures = JSON.parse(env.LAB_PRINCIPALS);
      if (!Object.hasOwn(fixtures, tenant)) throw new HttpError(404, "Unknown lab tenant");
      const authorization = request.headers.get("authorization");
      if (!authorization) throw new HttpError(401, "Lab principal required");
      if (authorization !== `Bearer ${fixtures[tenant]}`) throw new HttpError(403, "Wrong lab tenant");
      // Deliberate red control, enabled only by the experiment runner.
      const name = env.LAB_SHARED_CELL === "1" ? "broken-shared-cell" : tenant;
      url.pathname = path;
      return await env.TENANTS.getByName(name).fetch(new Request(url, request));
    } catch (error) {
      return replyError(error);
    }
  }
};

export class TenantCell {
  constructor(ctx) {
    this.ctx = ctx;
    this.sql = ctx.storage.sql;
    ctx.storage.transactionSync(() => {
      this.sql.exec(`CREATE TABLE IF NOT EXISTS entries (
        id TEXT PRIMARY KEY, identifier TEXT NOT NULL UNIQUE,
        date INTEGER NOT NULL, document TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0
      )`);
      this.sql.exec("CREATE INDEX IF NOT EXISTS entries_date ON entries(deleted, date DESC, id)");
      this.sql.exec(`CREATE TABLE IF NOT EXISTS receipts (
        operation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL
      )`);
    });
  }

  rows(query, ...bindings) {
    return this.sql.exec(query, ...bindings).toArray();
  }

  async fetch(request) {
    try {
      const url = new URL(request.url);
      if (request.method === "GET" && url.pathname === "/meta") {
        return Response.json({
          cellId: this.ctx.id.toString(),
          databaseSizeBytes: this.sql.databaseSize,
          records: this.rows("SELECT count(*) AS n FROM entries")[0].n,
          receipts: this.rows("SELECT count(*) AS n FROM receipts")[0].n,
          datePlan: this.rows(`EXPLAIN QUERY PLAN SELECT document FROM entries
            WHERE deleted = 0 AND date >= ? ORDER BY date DESC, id LIMIT ?`, 0, 10)
        });
      }
      if (request.method === "GET" && url.pathname === "/entries") {
        const since = integer(url, "since", 0);
        const limit = integer(url, "limit", 100, 1000);
        const skip = integer(url, "skip", 0);
        const includeDeleted = integer(url, "includeDeleted", 0, 1);
        const bindings = [since];
        let where = "date >= ?";
        if (!includeDeleted) where += " AND deleted = 0";
        if (url.searchParams.has("sgvGte")) {
          where += " AND json_type(document, '$.sgv') IN ('integer', 'real') AND json_extract(document, '$.sgv') >= ?";
          bindings.push(integer(url, "sgvGte", 0));
        }
        if (url.searchParams.has("sgv")) {
          requireValue(url.searchParams.get("sgv") === "null", "Only the lab null predicate is supported");
          where += " AND (json_type(document, '$.sgv') IS NULL OR json_type(document, '$.sgv') = 'null')";
        }
        bindings.push(limit, skip);
        return Response.json(this.rows(`SELECT document, deleted FROM entries WHERE ${where}
          ORDER BY date DESC, id LIMIT ? OFFSET ?`, ...bindings)
          .map(row => ({ document: JSON.parse(row.document), deleted: Boolean(row.deleted) })));
      }
      if (!["PUT", "DELETE"].includes(request.method)) throw new HttpError(405, "Unsupported lab method");
      requireValue(!url.search, "Mutation queries are unsupported");
      requireValue(request.headers.get("content-type")?.startsWith("application/json"), "JSON required");
      let body;
      try {
        body = await request.json();
      } catch (error) {
        if (error instanceof SyntaxError) throw new HttpError(400, "Invalid JSON");
        throw error;
      }
      requireValue(body && typeof body === "object" && !Array.isArray(body), "Object required");
      requireValue(typeof body.operationId === "string" && /^[a-z0-9-]{1,100}$/.test(body.operationId), "Invalid operationId");
      const fingerprint = JSON.stringify([request.method, url.pathname, body]);
      let result;
      try {
        result = this.ctx.storage.transactionSync(() => {
          const previous = this.rows("SELECT * FROM receipts WHERE operation_id = ?", body.operationId)[0];
          if (previous) {
            if (previous.fingerprint !== fingerprint) throw new HttpError(409, "Operation ID reused for different content");
            return { ...JSON.parse(previous.response), replay: true };
          }
          let changed = 0;
          if (request.method === "PUT") {
            requireValue(url.pathname === "/entries", "Invalid write route");
            requireValue(Array.isArray(body.entries) && body.entries.length > 0 && body.entries.length <= 1000, "Invalid batch");
            for (const doc of body.entries) {
              requireValue(doc && typeof doc === "object" && !Array.isArray(doc), "Invalid entry");
              requireValue(typeof doc._id === "string" && /^[a-z0-9-]{1,100}$/.test(doc._id), "Invalid _id");
              requireValue(typeof doc.identifier === "string" && doc.identifier.length > 0 && doc.identifier.length <= 100, "Invalid identifier");
              requireValue(Number.isSafeInteger(doc.date) && doc.date >= 0, "Invalid date");
              const old = this.rows("SELECT identifier, deleted FROM entries WHERE id = ?", doc._id)[0];
              if (old && old.identifier !== doc.identifier) throw new HttpError(409, "Identity is immutable");
              if (old?.deleted) throw new HttpError(409, "Explicit restore is not implemented");
              this.sql.exec(`INSERT INTO entries(id, identifier, date, document) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET date = excluded.date, document = excluded.document`,
              doc._id, doc.identifier, doc.date, JSON.stringify(doc));
              changed++;
            }
          } else {
            const id = /^\/entries\/([a-z0-9-]+)$/.exec(url.pathname)?.[1];
            requireValue(id, "Invalid delete route");
            this.sql.exec("UPDATE entries SET deleted = 1 WHERE id = ? AND deleted = 0", id);
            changed = this.rows("SELECT changes() AS n")[0].n;
          }
          const response = { changed, replay: false };
          this.sql.exec("INSERT INTO receipts VALUES (?, ?, ?)", body.operationId, fingerprint, JSON.stringify(response));
          return response;
        });
      } catch (error) {
        if (String(error.message).includes("UNIQUE constraint failed: entries.identifier")) {
          throw new HttpError(409, "Identifier already exists");
        }
        throw error;
      }
      return Response.json(result);
    } catch (error) {
      return replyError(error);
    }
  }
}
