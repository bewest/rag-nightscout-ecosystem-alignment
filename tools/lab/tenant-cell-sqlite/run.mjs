import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { appendFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";

const root = path.dirname(fileURLToPath(import.meta.url));
const binary = process.env.CELLD_BIN;
assert(binary, "Set CELLD_BIN to the pinned celld v0.6.3 executable");
const version = execFileSync(binary, ["--version"], { encoding: "utf8" }).trim();
assert.equal(version, "celld 0.6.3");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const principals = Object.fromEntries(Array.from({ length: 32 }, (_, i) =>
  [`tenant-${i}`, `synthetic-fixture-${i}-not-a-secret`]));
const report = {
  timestamp: new Date().toISOString(),
  runtime: {
    celld: version, node: process.version, platform: os.platform(), arch: os.arch(),
    binarySha256: createHash("sha256").update(await fs.readFile(binary)).digest("hex"),
    workerSha256: createHash("sha256").update(await fs.readFile(path.join(root, "worker.mjs"))).digest("hex"),
    runnerSha256: createHash("sha256").update(await fs.readFile(fileURLToPath(import.meta.url))).digest("hex")
  },
  nightscoutReference: { commit: "61eb37335954ae42c91345a0823bd67331025165", use: "Contract source inspection only; not executed by this lab" },
  mode: "celld dev; local object store; no cloud bucket or fleet",
  checks: [],
  limitations: [
    "Not the Nightscout storage adapter or API; no MongoDB/PostgreSQL parity claim.",
    "Local process restart is not node/disk loss, fleet replication, or RPO=0 proof.",
    "Loopback microbenchmark; no production tenant capacity or hosting cost inference.",
    "Synthetic fixed principals, no production identity integration or real health records."
  ]
};

async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const port = server.address().port;
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  return port;
}

async function descendants(pid) {
  let children;
  try {
    children = await fs.readFile(`/proc/${pid}/task/${pid}/children`, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return [];
    throw error;
  }
  const ids = children.trim() ? children.trim().split(/\s+/).map(Number) : [];
  return [...ids, ...(await Promise.all(ids.map(descendants))).flat()];
}

async function aggregateRss(pid) {
  let bytes = 0;
  const pids = [pid, ...await descendants(pid)];
  for (const id of pids) {
    const text = await fs.readFile(`/proc/${id}/status`, "utf8");
    bytes += Number(/^VmRSS:\s+(\d+)/m.exec(text)?.[1] ?? 0) * 1024;
  }
  return { bytes, processCount: pids.length, meaning: "Sum of dev process-tree RSS; shared pages may be counted twice" };
}

async function fileBytes(directory) {
  let bytes = 0;
  for (const item of await fs.readdir(directory, { withFileTypes: true })) {
    const name = path.join(directory, item.name);
    bytes += item.isDirectory() ? await fileBytes(name) : (await fs.stat(name)).size;
  }
  return bytes;
}

async function fixture(label, shared = false) {
  const runs = path.join(root, ".runs");
  await fs.mkdir(runs, { recursive: true });
  const directory = await fs.mkdtemp(path.join(runs, `${label}-`));
  const config = JSON.parse(await fs.readFile(path.join(root, "wrangler.json"), "utf8"));
  config.vars = { LAB_PRINCIPALS: JSON.stringify(principals), LAB_SHARED_CELL: shared ? "1" : "0" };
  await fs.writeFile(path.join(directory, "wrangler.json"), JSON.stringify(config, null, 2));
  await fs.copyFile(path.join(root, "worker.mjs"), path.join(directory, "worker.mjs"));
  const port = await unusedPort();
  let child;
  let exited;
  let log = "";
  const base = `http://127.0.0.1:${port}`;
  async function stop(signal = "SIGTERM") {
    if (!child || child.exitCode !== null || child.signalCode !== null) return;
    const ids = (await descendants(child.pid)).reverse();
    child.kill(signal);
    for (const id of ids) {
      try { process.kill(id, signal); } catch (error) {
        if (error.code !== "ESRCH") throw error;
      }
    }
    let timer;
    try {
      await Promise.race([exited, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("celld stop timed out")), 45000);
      })]);
    } finally {
      clearTimeout(timer);
      for (const id of [child.pid, ...ids]) {
        try { process.kill(id, "SIGKILL"); } catch (error) {
          if (error.code !== "ESRCH") throw error;
        }
      }
      await exited;
    }
  }
  async function start() {
    child = spawn(binary, ["dev", directory, "--port", String(port), "--host", "127.0.0.1", "--no-watch", "--logs"], {
      cwd: directory,
      env: { ...process.env, NO_COLOR: "1" },
      stdio: ["ignore", "pipe", "pipe"]
    });
    exited = new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("exit", (code, signal) => resolve({ code, signal }));
    });
    const save = data => {
      log += data;
      appendFileSync(path.join(directory, "node.log"), data);
    };
    child.stdout.on("data", save);
    child.stderr.on("data", save);
    for (let i = 0; i < 200; i++) {
      if (child.exitCode !== null || child.signalCode !== null) throw new Error(`celld exited: ${log}`);
      let response;
      try { response = await fetch(`${base}/health`, { signal: AbortSignal.timeout(500) }); }
      catch (error) {
        if (!(error instanceof TypeError) && error.name !== "TimeoutError") throw error;
      }
      if (response?.ok && (await response.json()).lab === true) return;
      await sleep(100);
    }
    throw new Error(`celld readiness timed out: ${log}`);
  }
  async function request(tenant, method = "GET", suffix = "/entries", body, expected = 200, principal = principals[tenant]) {
    const response = await fetch(`${base}/lab/${tenant}${suffix}`, {
      method,
      headers: { ...(principal ? { authorization: `Bearer ${principal}` } : {}), "content-type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(15000)
    });
    const value = await response.json();
    assert.equal(response.status, expected, `${JSON.stringify(value)}\n${log.slice(-3000)}`);
    return value;
  }
  return {
    directory, start, stop, request,
    rss: () => aggregateRss(child.pid),
    log: () => log
  };
}

const entry = (id, sgv, date = 1000) => ({ _id: id, identifier: `sync-${id}`, date, sgv });
const batch = (operationId, ...entries) => ({ operationId, entries });

async function check(name, run) {
  const started = performance.now();
  await run();
  report.checks.push({ name, passed: true, elapsedMs: performance.now() - started });
  console.log(`PASS ${name}`);
}

async function isolation(lab) {
  await lab.request("tenant-0", "PUT", "/entries", batch("isolation-a", entry("same", 100)));
  await lab.request("tenant-1", "PUT", "/entries", batch("isolation-b", entry("same", 200)));
  assert.equal((await lab.request("tenant-0"))[0].document.sgv, 100);
  assert.equal((await lab.request("tenant-1"))[0].document.sgv, 200);
  const a = await lab.request("tenant-0", "GET", "/meta");
  const b = await lab.request("tenant-1", "GET", "/meta");
  assert.notEqual(a.cellId, b.cellId);
  return { a, b };
}

let lab;
let red;
try {
  lab = await fixture("positive");
  await lab.start();
  report.emptyRss = await lab.rss();
  await check("overlapping record IDs stay tenant-local", async () => {
    report.initialCells = await isolation(lab);
  });
  await check("wrong tenant principal and unknown/unbound routes refuse reads and writes", async () => {
    for (const method of ["GET", "PUT", "DELETE"]) {
      const suffix = method === "DELETE" ? "/entries/same" : "/entries";
      const body = method === "GET" ? undefined : batch("forged", entry("forged", 999));
      await lab.request("tenant-1", method, suffix, body, 403, principals["tenant-0"]);
      await lab.request("tenant-0", method, suffix, body, 401, "");
      await lab.request("unknown", method, suffix, body, 404, principals["tenant-0"]);
    }
    assert.equal((await lab.request("tenant-0")).length, 1);
    assert.equal((await lab.request("tenant-1")).length, 1);
  });
  await check("concurrent retries commit once; receipts are tenant-local; changed-content reuse conflicts", async () => {
    const body = batch("repeat-op", entry("repeat", 121));
    const values = await Promise.all(Array.from({ length: 16 }, () => lab.request("tenant-0", "PUT", "/entries", body)));
    assert.equal(values.filter(value => !value.replay).length, 1);
    await lab.request("tenant-0", "PUT", "/entries", batch("repeat-new-op", entry("repeat", 121)));
    assert.equal((await lab.request("tenant-0")).filter(row => row.document._id === "repeat").length, 1);
    assert.equal((await lab.request("tenant-1", "PUT", "/entries",
      batch("repeat-op", entry("repeat", 222)))).replay, false);
    await lab.request("tenant-0", "PUT", "/entries", batch("repeat-op", entry("repeat", 999)), 409);
    assert.equal((await lab.request("tenant-0")).find(row => row.document._id === "repeat").document.sgv, 121);
  });
  await check("batch conflict rolls back earlier rows and receipt", async () => {
    const before = await lab.request("tenant-0", "GET", "/meta");
    await lab.request("tenant-0", "PUT", "/entries", batch("rollback",
      entry("rolled-back", 111), { ...entry("conflict", 123), identifier: "sync-same" }), 409);
    const after = await lab.request("tenant-0", "GET", "/meta");
    assert.equal(after.records, before.records);
    assert.equal(after.receipts, before.receipts);
    assert(!(await lab.request("tenant-0")).some(row => row.document._id === "rolled-back"));
    assert.equal((await lab.request("tenant-0", "PUT", "/entries", batch("rollback", entry("rollback-retry", 122)))).replay, false);
  });
  await check("JSON null/missing and numeric/string predicates remain distinct", async () => {
    const missing = entry("missing", 100, 2000);
    delete missing.sgv;
    await lab.request("tenant-0", "PUT", "/entries", batch("types",
      entry("numeric", 150, 2000), entry("string", "150", 2000), entry("null", null, 2000), missing));
    assert.deepEqual((await lab.request("tenant-0", "GET", "/entries?since=2000&sgvGte=140"))
      .map(row => row.document._id), ["numeric"]);
    const values = await lab.request("tenant-0", "GET", "/entries?since=2000&sgv=null");
    assert.deepEqual(values.map(row => row.document._id), ["missing", "null"]);
    assert.equal(Object.hasOwn(values[0].document, "sgv"), false);
    assert.equal(values[1].document.sgv, null);
  });
  await check("stable date/id pagination and indexed date query", async () => {
    const all = await lab.request("tenant-0", "GET", "/entries?since=2000");
    assert.deepEqual((await lab.request("tenant-0", "GET", "/entries?since=2000&skip=1&limit=2")), all.slice(1, 3));
    await lab.request("tenant-0", "GET", "/entries?limit=-1", undefined, 400);
    await lab.request("tenant-0", "GET", "/entries?limit=1001", undefined, 400);
    assert((await lab.request("tenant-0", "GET", "/meta")).datePlan.some(row => row.detail.includes("entries_date")));
  });
  await check("tombstone survives resend and does not affect the other tenant", async () => {
    await lab.request("tenant-0", "DELETE", "/entries/same", { operationId: "delete-same" });
    assert(!(await lab.request("tenant-0")).some(row => row.document._id === "same"));
    assert((await lab.request("tenant-0", "GET", "/entries?includeDeleted=1")).find(row => row.document._id === "same").deleted);
    await lab.request("tenant-0", "PUT", "/entries", batch("resurrect", entry("same", 333)), 409);
    assert.equal((await lab.request("tenant-1")).find(row => row.document._id === "same").document.sgv, 200);
  });
  await check("parallel distinct writes do not lose records", async () => {
    await Promise.all(Array.from({ length: 24 }, (_, i) => lab.request("tenant-0", "PUT", "/entries",
      batch(`parallel-${i}`, entry(`parallel-${i}`, 100 + i, 3000)))));
    assert.equal((await lab.request("tenant-0", "GET", "/entries?since=3000")).length, 24);
  });
  await check("one synthetic CGM day per each of 32 tenants", async () => {
    const started = performance.now();
    for (const tenant of Object.keys(principals)) {
      const entries = Array.from({ length: 288 }, (_, i) => entry(`cgm-${i}`, 90 + i % 60, 1700000000000 + i * 300000));
      await lab.request(tenant, "PUT", "/entries", { operationId: "cgm-day", entries });
      const rows = await lab.request(tenant, "GET", "/entries?since=1700000000000&limit=1000");
      assert.equal(rows.length, 288);
      assert.deepEqual(rows[0].document, entries[287]);
    }
    report.workload = { tenants: 32, entriesPerTenant: 288, writesBatchedPerTenant: 1, elapsedMs: performance.now() - started };
    report.afterWorkloadRss = await lab.rss();
    report.afterWorkloadLocalStoreBytes = await fileBytes(path.join(lab.directory, ".celld"));
  });
  await check("warm sequential loopback write/read latency", async () => {
    const writes = [], reads = [];
    for (let i = 0; i < 120; i++) {
      let started = performance.now();
      await lab.request("tenant-0", "PUT", "/entries", batch(`timed-${i}`, entry(`timed-${i}`, 120, 4000)));
      writes.push(performance.now() - started);
      started = performance.now();
      await lab.request("tenant-0", "GET", "/entries?limit=10");
      reads.push(performance.now() - started);
    }
    const summarize = values => {
      const sorted = [...values].sort((a, b) => a - b);
      return { samples: sorted.length, p50Ms: sorted[Math.ceil(sorted.length * 0.5) - 1], p95Ms: sorted[Math.ceil(sorted.length * 0.95) - 1] };
    };
    report.loopbackLatency = { writes: summarize(writes), reads: summarize(reads) };
  });
  const snapshots = {};
  for (const tenant of Object.keys(principals)) {
    snapshots[tenant] = await lab.request(tenant, "GET", "/entries?includeDeleted=1&limit=1000");
  }
  for (const signal of ["SIGTERM", "SIGKILL"]) {
    await check(`${signal} restart preserves acknowledged documents, tombstones, cell IDs and receipts`, async () => {
      await lab.stop(signal);
      await lab.start();
      for (const tenant of Object.keys(principals)) {
        assert.deepEqual(await lab.request(tenant, "GET", "/entries?includeDeleted=1&limit=1000"), snapshots[tenant]);
      }
      assert.equal((await lab.request("tenant-0", "GET", "/meta")).cellId, report.initialCells.a.cellId);
      assert.equal((await lab.request("tenant-0", "PUT", "/entries", batch("repeat-op", entry("repeat", 121)))).replay, true);
      await lab.request("tenant-0", "PUT", "/entries", batch("repeat-op", entry("repeat", 999)), 409);
    });
  }
  report.finalMeta = await lab.request("tenant-0", "GET", "/meta");
  await lab.stop();
  red = await fixture("shared-cell-control", true);
  await red.start();
  let detected;
  try { await isolation(red); } catch (error) {
    if (error.code !== "ERR_ASSERTION") throw error;
    assert.equal(error.actual, 200, "The red control must expose tenant B's value through tenant A");
    assert.equal(error.expected, 100);
    detected = error.message;
  }
  assert(detected, "Isolation test must fail when both tenants deliberately share a cell");
  report.negativeControl = { name: "shared-cell routing", rejected: true, assertion: detected };
  console.log("PASS shared-cell negative control is detected");
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.error = error.stack;
  console.error(error);
  process.exitCode = 1;
} finally {
  for (const fixture of [lab, red]) {
    if (fixture) {
      await fixture.stop();
      await fs.writeFile(path.join(fixture.directory, "node.log"), fixture.log());
    }
  }
  await fs.mkdir(path.join(root, "results"), { recursive: true });
  await fs.writeFile(path.join(root, "results", "local.json"), `${JSON.stringify(report, null, 2)}\n`);
}
