// Measure every rendered SVG against the model it was drawn from.
//   node measure.js <build dir> <chrome>   prints JSON to stdout
// Extends tools/lab/stpa-diagrams/measure.js with the metrics for "elbows crossing each other,
// hard to follow": turning per edge, axis-aligned share, label text over lines, loop pairs drawn
// straight and parallel, grid alignment of node centres. Geometry is read in Chrome at the SVG's
// intrinsic (viewBox) size, so every tool's transforms are applied and units are comparable.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const [BUILD, CHROME] = process.argv.slice(2);
const VARIANTS = ['dot-spline', 'grid', 'grid-z', 'neato-ortho', 'elk', 'avoid', 'control-grid', 'control-random'];

function extract(args) {
  const { variant, model } = args;
  const svg = document.querySelector('svg');
  const vb = svg.viewBox && svg.viewBox.baseVal;
  if (vb && vb.width) { svg.setAttribute('width', vb.width); svg.setAttribute('height', vb.height); }
  const box = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
  const shapeBox = (g) => {
    let best = null;
    for (const el of g.querySelectorAll('rect, path, polygon, ellipse')) {
      const r = el.getBoundingClientRect();
      if (!best || r.width * r.height > best.width * best.height) best = r;
    }
    return best && { x: best.x, y: best.y, w: best.width, h: best.height };
  };
  const sample = (p) => {
    const len = p.getTotalLength();
    const m = p.getScreenCTM();
    const pts = [];
    const n = Math.max(2, Math.ceil(len / 2));
    for (let i = 0; i <= n; i++) {
      const q = p.getPointAtLength((len * i) / n);
      pts.push([m.a * q.x + m.c * q.y + m.e, m.b * q.x + m.d * q.y + m.f]);
    }
    return pts;
  };
  const longest = (g) => [...g.querySelectorAll('path')].sort((a, b) => b.getTotalLength() - a.getTotalLength())[0];
  const nodes = {}, edges = {};
  const ids = new Set(model.nodes.map((n) => n.id));
  if (/^(dot|neato)-/.test(variant)) {
    for (const id of ids) { const g = svg.querySelector('#n_' + id); if (g) nodes[id] = shapeBox(g); }
    for (const e of model.edges) { const g = svg.querySelector('#e_' + e.k); if (g && longest(g)) edges[e.k] = sample(longest(g)); }
  } else {
    svg.querySelectorAll('g.node').forEach((g) => (nodes[g.dataset.id] = shapeBox(g)));
    svg.querySelectorAll('path.edge').forEach((p) => (edges[p.dataset.k] = sample(p)));
  }
  const texts = [];
  for (const el of svg.querySelectorAll('text')) {
    const b = box(el);
    if (b.w > 1 && b.h > 1 && (el.textContent || '').trim()) texts.push(Object.assign(b, { s: el.textContent.trim() }));
  }
  const r = svg.getBoundingClientRect();
  return { nodes, edges, texts, width: r.width, height: r.height };
}

// ---------------------------------------------------------------- scoring

const ctr = (b) => [b.x + b.w / 2, b.y + b.h / 2];
const inside = (b, p, pad) => p[0] > b.x - pad && p[0] < b.x + b.w + pad && p[1] > b.y - pad && p[1] < b.y + b.h + pad;

function segX(p1, p2, p3, p4) {
  const d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
  if (Math.abs(d) < 1e-9) return null;
  const t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d;
  const u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d;
  return t > 0 && t < 1 && u > 0 && u < 1 ? [p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])] : null;
}
const minDist = (pt, pts) => Math.min(...pts.map((q) => Math.hypot(q[0] - pt[0], q[1] - pt[1])));
const middle = (pts) => pts.slice(Math.floor(pts.length * 0.1), Math.ceil(pts.length * 0.9));

// Shape of one sampled path: total turning in right angles, axis-aligned share of its length,
// and whether it is one straight vertical run.
function shape(pts) {
  let turn = 0, len = 0, axis = 0, prev = null;
  for (let i = 0; i + 1 < pts.length; i++) {
    const dx = pts[i + 1][0] - pts[i][0], dy = pts[i + 1][1] - pts[i][1];
    const l = Math.hypot(dx, dy);
    if (l < 0.3) continue;
    const a = Math.atan2(dy, dx);
    len += l;
    const off = Math.abs(((a % (Math.PI / 2)) + Math.PI / 2) % (Math.PI / 2));
    if (Math.min(off, Math.PI / 2 - off) < (3 * Math.PI) / 180) axis += l;
    if (prev !== null) {
      let d = a - prev;
      while (d > Math.PI) d -= 2 * Math.PI;
      while (d < -Math.PI) d += 2 * Math.PI;
      turn += Math.abs(d);
    }
    prev = a;
  }
  const xs = pts.map((p) => p[0]);
  return { bends: turn / (Math.PI / 2), axis: len ? axis / len : 0, len,
    vertical: Math.max(...xs) - Math.min(...xs) < 1.5 && turn < 0.1 };
}

function score(model, g, expected) {
  const out = {};
  const missingN = model.nodes.filter((n) => !g.nodes[n.id]).map((n) => n.id);
  const missingE = model.edges.filter((e) => !g.edges[e.k]).map((e) => e.k);
  out.found = { nodes: model.nodes.length - missingN.length, of_nodes: model.nodes.length,
    edges: model.edges.length - missingE.length, of_edges: model.edges.length, missing_nodes: missingN, missing_edges: missingE };
  if (missingN.length || missingE.length) return out;
  const N = model.nodes, E = model.edges;
  const C = Object.fromEntries(N.map((n) => [n.id, ctr(g.nodes[n.id])]));
  // hierarchy and lanes (as in the old lab)
  let lv = 0, lvT = 0, col = 0, colT = 0;
  for (const a of N) for (const b of N) {
    if (a.level < b.level) { lvT++; if (C[a.id][1] >= C[b.id][1] - 1) lv++; }
    if (a.level === b.level && a.column < b.column) { colT++; if (C[a.id][0] >= C[b.id][0] - 1) col++; }
  }
  out.level_violations = [lv, lvT];
  out.column_violations = [col, colT];
  // grid alignment: spread of centre y within a level, of centre x within a column
  const spread = (key, axis) => {
    const groups = {};
    for (const n of N) (groups[n[key]] = groups[n[key]] || []).push(C[n.id][axis]);
    return Object.values(groups).filter((v) => v.length > 1).map((v) => Math.max(...v) - Math.min(...v));
  };
  const sp = [...spread('level', 1), ...spread('column', 0)];
  out.grid_max_dev = +Math.max(0, ...sp).toFixed(1);
  out.grid_misaligned = [sp.filter((s) => s > 2).length, sp.length];
  // edge shape
  const S = Object.fromEntries(E.map((e) => [e.k, shape(g.edges[e.k])]));
  const sum = (f) => E.reduce((s, e) => s + f(S[e.k]), 0);
  out.bends_mean = +(sum((s) => s.bends) / E.length).toFixed(2);
  out.bends_max = +Math.max(...E.map((e) => S[e.k].bends)).toFixed(2);
  out.axis_share = +(sum((s) => s.axis * s.len) / sum((s) => s.len)).toFixed(3);
  if (expected) {
    out.bends_check_max_err = +Math.max(...E.map((e) => Math.abs(S[e.k].bends - expected.bends[e.k]))).toFixed(2);
  }
  // loop pairs: control left, distinct, both straight vertical, parallel at constant separation
  let side = 0, distinct = 0, straight = 0, parallel = 0;
  for (const [a, b] of model.loop_pairs) {
    const ctl = E.find((e) => e.kind === 'control' && [e.from, e.to].sort().join() === [a, b].join());
    const fb = E.find((e) => e.kind === 'feedback' && [e.from, e.to].sort().join() === [a, b].join());
    const pc = g.edges[ctl.k], pf = g.edges[fb.k];
    const mc = middle(pc), mf = middle(pf);
    const mx = (ps) => ps.reduce((s, p) => s + p[0], 0) / ps.length;
    if (mx(mc) < mx(mf) - 2) side++;
    const d = mc.map((p) => minDist(p, pf));
    if (Math.min(...d) > 6) distinct++;
    if (S[ctl.k].vertical && S[fb.k].vertical) straight++;
    const med = [...d].sort((x, y) => x - y)[Math.floor(d.length / 2)];
    out.pair_detail = (out.pair_detail || []).concat([[a, b, +Math.min(...d).toFixed(1), +Math.max(...d).toFixed(1), +S[ctl.k].bends.toFixed(2), +S[fb.k].bends.toFixed(2)]]);
    if (Math.min(...d) > 6 && Math.round(S[ctl.k].bends) === Math.round(S[fb.k].bends) &&
        Math.max(...d) - Math.min(...d) <= Math.max(8, 0.5 * med)) parallel++;
  }
  const L = model.loop_pairs.length;
  out.loops_control_left = [side, L];
  out.loops_distinct = [distinct, L];
  out.loops_straight = [straight, L];
  out.loops_parallel = [parallel, L];
  // overlaps and crossings (crossings near nodes ignored, as in the old lab)
  const boxes = N.map((n) => g.nodes[n.id]);
  let overlap = 0, cross = 0;
  for (let i = 0; i < E.length; i++) for (let j = i + 1; j < E.length; j++) {
    const A = g.edges[E[i].k], B = g.edges[E[j].k];
    const [s, l] = A.length < B.length ? [A, B] : [B, A];
    const ms = middle(s);
    if (ms.filter((p) => minDist(p, l) < 3).length > 0.3 * ms.length) { overlap++; continue; }
    const hits = [];
    for (let p = 0; p + 1 < A.length; p++) for (let q = 0; q + 1 < B.length; q++) {
      const x = segX(A[p], A[p + 1], B[q], B[q + 1]);
      if (x && !boxes.some((b) => inside(b, x, 10)) && !hits.some((h) => Math.hypot(h[0] - x[0], h[1] - x[1]) < 10)) hits.push(x);
    }
    cross += hits.length;
  }
  out.edge_overlaps = overlap;
  out.crossings = cross;
  let through = 0;
  for (const e of E) for (const n of N) {
    if (n.id === e.from || n.id === e.to) continue;
    const b = g.nodes[n.id], pts = g.edges[e.k];
    if (pts.some((p, i) => i + 1 < pts.length && inside(b, p, -3) && inside(b, pts[i + 1], -3))) through++;
  }
  out.edges_through_nodes = through;
  let intr = 0;
  for (const gr of model.groups) {
    const mem = N.filter((n) => n.group === gr.id).map((n) => g.nodes[n.id]);
    if (!mem.length) continue;
    const hull = { x: Math.min(...mem.map((b) => b.x)), y: Math.min(...mem.map((b) => b.y)) };
    hull.w = Math.max(...mem.map((b) => b.x + b.w)) - hull.x;
    hull.h = Math.max(...mem.map((b) => b.y + b.h)) - hull.y;
    intr += N.filter((n) => n.group !== gr.id && inside(hull, C[n.id], 0)).length;
  }
  out.group_intrusions = model.groups.length ? intr : null;
  // text over text (old lab) and label text over any edge line (new): a text run outside every
  // node box whose box, shrunk by 1, contains a sampled point of any edge
  let coll = 0;
  const T = g.texts;
  for (let i = 0; i < T.length; i++) for (let j = i + 1; j < T.length; j++) {
    const a = T[i], b = T[j];
    const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (ox > 0 && oy > 0 && ox * oy > 0.15 * Math.min(a.w * a.h, b.w * b.h)) coll++;
  }
  out.label_collisions = coll;
  const free = T.filter((t) => !boxes.some((b) => inside(b, ctr(t), 0)));
  const shrink = (t) => ({ x: t.x + 1, y: t.y + 1, w: t.w - 2, h: t.h - 2 });
  const over = free.filter((t) => E.some((e) => g.edges[e.k].some((p) => inside(shrink(t), p, 0))));
  out.label_over_line = [over.length, free.length];
  out.label_over_line_texts = over.map((t) => t.s);
  out.width = Math.round(g.width);
  out.height = Math.round(g.height);
  out.area_per_node = Math.round((g.width * g.height) / N.length);
  return out;
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 2400, height: 2400 } });
  const results = [];
  for (const dia of fs.readdirSync(BUILD).filter((d) => fs.statSync(path.join(BUILD, d)).isDirectory()).sort()) {
    const dir = path.join(BUILD, dia);
    const model = JSON.parse(fs.readFileSync(path.join(dir, 'model.json')));
    for (const v of VARIANTS) {
      const file = path.join(dir, v + '.svg');
      const row = { diagram: dia, variant: v };
      if (!fs.existsSync(file)) { row.error = 'no svg'; results.push(row); continue; }
      await page.setContent('<!doctype html><body style="margin:0">' + fs.readFileSync(file, 'utf8').replace(/<\?xml[^>]*>/, '') + '</body>');
      const g = await page.evaluate(extract, { variant: v, model });
      const exp = path.join(dir, v + '.expected.json');
      Object.assign(row, score(model, g, fs.existsSync(exp) ? JSON.parse(fs.readFileSync(exp)) : null));
      results.push(row);
    }
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})();
