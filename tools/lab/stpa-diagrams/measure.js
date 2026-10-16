// Measure every rendered SVG against the model it was generated from.
//   node measure.js <build dir> <chrome>   prints JSON to stdout
// Geometry is read in the browser (screen coordinates, so every tool's transforms are applied),
// then scored here. A variant whose nodes or edges cannot all be found is reported, not scored.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const [BUILD, CHROME] = process.argv.slice(2);
const VARIANTS = ['control-grid', 'control-random', 'dot-spline', 'dot-ortho', 'd2-dagre', 'd2-elk', 'd2-grid',
  'mermaid-dagre', 'mermaid-elk', 'plantuml'];

// In-page extraction: returns {nodes: {id: box}, edges: {k: [[x,y]...]}, width, height} or {error}
function extract(args) {
  const { variant, model } = args;
  const svg = document.querySelector('svg');
  // measure at intrinsic size: some tools emit width="100%" or nested <svg>s sized by viewBox
  const vb = svg.viewBox && svg.viewBox.baseVal;
  if (vb && vb.width) { svg.setAttribute('width', vb.width); svg.setAttribute('height', vb.height); }
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
    const n = Math.max(2, Math.ceil(len / 3));
    for (let i = 0; i <= n; i++) {
      const q = p.getPointAtLength((len * i) / n);
      pts.push([m.a * q.x + m.c * q.y + m.e, m.b * q.x + m.d * q.y + m.f]);
    }
    return pts;
  };
  const longest = (g) => [...g.querySelectorAll('path')].sort((a, b) => b.getTotalLength() - a.getTotalLength())[0];
  const nodes = {};
  const edges = {};
  const ids = new Set(model.nodes.map((n) => n.id));
  const pairIndex = {}; // (from,to) occurrence -> k, for tools that number edges per pair
  for (const e of model.edges) {
    const key = e.from + '>' + e.to;
    pairIndex[key] = pairIndex[key] || [];
    pairIndex[key].push(e.k);
  }
  const dec = (s) => { try { return atob(s); } catch { return null; } };
  if (variant.startsWith('control')) {
    svg.querySelectorAll('g.node').forEach((g) => (nodes[g.dataset.id] = shapeBox(g)));
    svg.querySelectorAll('path.edge').forEach((p) => (edges[p.dataset.k] = sample(p)));
  } else if (variant.startsWith('dot')) {
    for (const id of ids) { const g = svg.querySelector('#n_' + id); if (g) nodes[id] = shapeBox(g); }
    for (const e of model.edges) { const g = svg.querySelector('#e_' + e.k); if (g) edges[e.k] = sample(longest(g)); }
  } else if (variant.startsWith('d2')) {
    for (const g of svg.querySelectorAll('g[class]')) {
      const d = dec(g.classList[0]);
      if (!d) continue;
      const txt = d.replace(/&gt;/g, '>');
      // edges are "(a -> b)[i]", prefixed with the container when both ends share one
      const em = txt.match(/^(?:[^(]+\.)?\((.+) -> (.+)\)\[(\d+)\]$/);
      if (em) {
        const last = (s) => s.split('.').pop();
        const ks = pairIndex[last(em[1]) + '>' + last(em[2])];
        const p = g.querySelector('path.connection') || longest(g);
        if (ks && ks[+em[3]] !== undefined && p) edges[ks[+em[3]]] = sample(p);
      } else {
        const id = txt.split('.').pop();
        const shape = g.querySelector(':scope > g.shape');
        if (ids.has(id) && shape) nodes[id] = shapeBox(shape);
      }
    }
  } else if (variant.startsWith('mermaid')) {
    for (const g of svg.querySelectorAll('g.node')) {
      const m = g.id.match(/flowchart-(.+)-\d+$/);
      if (m && ids.has(m[1])) nodes[m[1]] = shapeBox(g);
    }
    for (const p of svg.querySelectorAll('path')) {
      const m = p.id.match(/(?:^|-)e(\d+)(?:_\d+)?$/);
      if (m) edges[m[1]] = sample(p);
    }
  } else if (variant === 'plantuml') {
    for (const g of svg.querySelectorAll('g.entity')) if (ids.has(g.dataset.entity)) nodes[g.dataset.entity] = shapeBox(g);
    for (const g of svg.querySelectorAll('g.link')) {
      const k = model.puml_lines[g.dataset.sourceLine];
      if (k !== undefined) edges[k] = sample(g.querySelector('path'));
    }
  }
  // every rendered text run, for the label-collision count (tool-agnostic: text boxes only)
  const texts = [];
  for (const el of svg.querySelectorAll('text, foreignObject p, foreignObject span.nodeLabel, foreignObject span.edgeLabel')) {
    if (el.closest('foreignObject') && el.tagName.toLowerCase() === 'span' && el.querySelector('p')) continue;
    const b = el.getBoundingClientRect();
    if (b.width > 1 && b.height > 1 && (el.textContent || '').trim()) texts.push({ x: b.x, y: b.y, w: b.width, h: b.height });
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
const middle = (pts) => pts.slice(Math.floor(pts.length * 0.2), Math.ceil(pts.length * 0.8));

function score(model, g) {
  const out = {};
  const missingN = model.nodes.filter((n) => !g.nodes[n.id]).map((n) => n.id);
  const missingE = model.edges.filter((e) => !g.edges[e.k]).map((e) => e.k);
  out.found = { nodes: model.nodes.length - missingN.length, of_nodes: model.nodes.length,
    edges: model.edges.length - missingE.length, of_edges: model.edges.length, missing_nodes: missingN, missing_edges: missingE };
  if (missingN.length || missingE.length) return out;
  const N = model.nodes;
  const C = Object.fromEntries(N.map((n) => [n.id, ctr(g.nodes[n.id])]));
  // hierarchy: every higher-level node above every lower-level node
  let lv = 0, lvT = 0, col = 0, colT = 0;
  for (const a of N) for (const b of N) {
    if (a.level < b.level) { lvT++; if (C[a.id][1] >= C[b.id][1] - 1) lv++; }
    if (a.level === b.level && a.column < b.column) { colT++; if (C[a.id][0] >= C[b.id][0] - 1) col++; }
  }
  out.level_violations = [lv, lvT];
  out.column_violations = [col, colT];
  // STPA loops: control path left of its feedback path, and drawn as two distinct paths
  let side = 0, distinct = 0;
  for (const [a, b] of model.loop_pairs) {
    const ctl = model.edges.find((e) => e.kind === 'control' && [e.from, e.to].sort().join() === [a, b].join());
    const fb = model.edges.find((e) => e.kind === 'feedback' && [e.from, e.to].sort().join() === [a, b].join());
    const mc = middle(g.edges[ctl.k]), mf = middle(g.edges[fb.k]);
    const mx = (ps) => ps.reduce((s, p) => s + p[0], 0) / ps.length;
    if (mx(mc) < mx(mf) - 2) side++;
    if (Math.min(...mc.map((p) => minDist(p, mf))) > 6) distinct++;
  }
  out.loops_control_left = [side, model.loop_pairs.length];
  out.loops_distinct = [distinct, model.loop_pairs.length];
  // edges drawn on top of each other, then crossings among the rest (ignoring the area around nodes)
  const E = model.edges;
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
  // edges that run through a node they do not touch
  let through = 0;
  for (const e of E) for (const n of N) {
    if (n.id === e.from || n.id === e.to) continue;
    const b = g.nodes[n.id];
    const pts = g.edges[e.k];
    if (pts.some((p, i) => i + 1 < pts.length && inside(b, p, -3) && inside(b, pts[i + 1], -3))) through++;
  }
  out.edges_through_nodes = through;
  // groups: no outside node sits inside the hull of a group's members
  let intr = 0;
  for (const gr of model.groups) {
    const mem = N.filter((n) => n.group === gr.id).map((n) => g.nodes[n.id]);
    const hull = { x: Math.min(...mem.map((b) => b.x)), y: Math.min(...mem.map((b) => b.y)) };
    hull.w = Math.max(...mem.map((b) => b.x + b.w)) - hull.x;
    hull.h = Math.max(...mem.map((b) => b.y + b.h)) - hull.y;
    intr += N.filter((n) => n.group !== gr.id && inside(hull, C[n.id], 0)).length;
  }
  out.group_intrusions = model.groups.length ? intr : null;
  // text runs overlapping by more than 15% of the smaller one's area
  let coll = 0;
  const T = g.texts;
  for (let i = 0; i < T.length; i++) for (let j = i + 1; j < T.length; j++) {
    const a = T[i], b = T[j];
    const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (ox > 0 && oy > 0 && ox * oy > 0.15 * Math.min(a.w * a.h, b.w * b.h)) coll++;
  }
  out.label_collisions = coll;
  out.text_runs = T.length;
  out.width = Math.round(g.width);
  out.height = Math.round(g.height);
  return out;
}

// node centres normalised to the drawing's extent, compared base vs mutated
function displacement(model, a, b) {
  const norm = (g) => {
    const cs = model.nodes.map((n) => ctr(g.nodes[n.id]));
    const x0 = Math.min(...cs.map((c) => c[0])), x1 = Math.max(...cs.map((c) => c[0]));
    const y0 = Math.min(...cs.map((c) => c[1])), y1 = Math.max(...cs.map((c) => c[1]));
    return cs.map((c) => [(c[0] - x0) / (x1 - x0 || 1), (c[1] - y0) / (y1 - y0 || 1)]);
  };
  const A = norm(a), B = norm(b);
  const d = A.map((p, i) => Math.hypot(p[0] - B[i][0], p[1] - B[i][1]));
  return { mean: +(d.reduce((s, x) => s + x, 0) / d.length).toFixed(3), max: +Math.max(...d).toFixed(3) };
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 2400, height: 2400 } });
  const results = [];
  for (const dia of fs.readdirSync(BUILD).filter((d) => fs.statSync(path.join(BUILD, d)).isDirectory()).sort()) {
    const geo = {};
    for (const mode of ['base', 'mutated']) {
      const dir = path.join(BUILD, dia, mode);
      const model = JSON.parse(fs.readFileSync(path.join(dir, 'model.json')));
      const renders = Object.fromEntries(fs.readFileSync(path.join(dir, 'render.jsonl'), 'utf8').trim().split('\n')
        .map((l) => JSON.parse(l)).map((r) => [r.variant, r]));
      for (const v of VARIANTS) {
        const file = path.join(dir, v + '.svg');
        const row = { diagram: dia, mode, variant: v, render: renders[v] || null };
        if (!fs.existsSync(file)) { row.error = 'no svg'; results.push(row); continue; }
        await page.setContent('<!doctype html><body style="margin:0">' + fs.readFileSync(file, 'utf8') + '</body>');
        const g = await page.evaluate(extract, { variant: v, model });
        Object.assign(row, score(model, g));
        row.svg_bytes = fs.statSync(file).size;
        const src = fs.readdirSync(dir).find((f) => f.startsWith(v + '.') && !/\.(svg|log)$/.test(f));
        row.source_lines = src ? fs.readFileSync(path.join(dir, src), 'utf8').trim().split('\n').length : null;
        results.push(row);
        geo[mode + '/' + v] = { model, g, ok: !row.found.missing_nodes.length };
      }
    }
    for (const v of VARIANTS) {
      const a = geo['base/' + v], b = geo['mutated/' + v];
      const row = results.find((r) => r.diagram === dia && r.mode === 'mutated' && r.variant === v);
      if (a && b && a.ok && b.ok && row && !v.startsWith('control')) row.displacement = displacement(a.model, a.g, b.g);
    }
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 1));
})();
