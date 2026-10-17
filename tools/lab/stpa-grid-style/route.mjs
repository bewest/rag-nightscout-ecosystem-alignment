// Route one diagram with an external engine, for comparison with gridstpa.py's own router.
//   node route.mjs elk|avoid < job.json > result.json
// The job (written by lab.py) carries node boxes at their grid positions and, per edge, the two
// ports: side and absolute position. The result is {nodes: {id: [x, y, w, h]}, edges: {k: [[x, y], ...]},
// labels: {k: [x, y, w, h]}} (labels only from ELK; libavoid places none).
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

// the engines live in .tools/node (README, install); ESM ignores NODE_PATH, so resolve from there
const require = createRequire(new URL('./.tools/node/package.json', import.meta.url));

const engine = process.argv[2];
const job = JSON.parse(readFileSync(0, 'utf8'));
const out = { nodes: {}, edges: {}, labels: {} };

if (engine === 'elk') {
  const ELK = require('elkjs/lib/elk.bundled.js');
  const elk = new ELK();
  const SIDE = { top: 'NORTH', bottom: 'SOUTH', left: 'WEST', right: 'EAST' };
  const children = job.nodes.map((n) => ({
    id: n.id, x: n.x, y: n.y, width: n.w, height: n.h,
    layoutOptions: { 'elk.portConstraints': 'FIXED_POS' },
    ports: job.edges.flatMap((e) => [e.src, e.dst].filter((p) => p.id === n.id).map((p) => ({
      id: `${n.id}_${e.k}_${p === e.src ? 's' : 'd'}`, width: 1, height: 1,
      x: p.side === 'left' ? -1 : p.side === 'right' ? n.w : p.x - n.x,
      y: p.side === 'top' ? -1 : p.side === 'bottom' ? n.h : p.y - n.y,
      layoutOptions: { 'elk.port.side': SIDE[p.side] },
    }))),
  }));
  const graph = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.cycleBreaking.strategy': 'INTERACTIVE',
      'elk.layered.layering.strategy': 'INTERACTIVE',
      'elk.layered.crossingMinimization.strategy': 'INTERACTIVE',
      'elk.layered.nodePlacement.strategy': 'INTERACTIVE',
      'elk.spacing.nodeNode': '50',
      'elk.layered.spacing.nodeNodeBetweenLayers': '60',
      'elk.layered.spacing.edgeNodeBetweenLayers': '20',
      'elk.spacing.edgeEdge': '12',
      'elk.spacing.edgeLabel': '4',
      'elk.edgeLabels.placement': 'CENTER',
      'elk.layered.edgeLabels.sideSelection': 'SMART_DOWN',
    },
    children,
    edges: job.edges.map((e) => ({
      id: 'e' + e.k,
      sources: [`${e.src.id}_${e.k}_s`],
      targets: [`${e.dst.id}_${e.k}_d`],
      labels: [{ text: String(e.k), width: e.label.w, height: e.label.h }],
    })),
  };
  const res = await elk.layout(graph);
  for (const c of res.children) out.nodes[c.id] = [c.x, c.y, c.width, c.height];
  for (const e of res.edges) {
    const k = +e.id.slice(1);
    const pts = [];
    for (const s of e.sections || []) {
      pts.push([s.startPoint.x, s.startPoint.y]);
      for (const b of s.bendPoints || []) pts.push([b.x, b.y]);
      pts.push([s.endPoint.x, s.endPoint.y]);
    }
    out.edges[k] = pts;
    const l = (e.labels || [])[0];
    if (l) out.labels[k] = [l.x, l.y, l.width, l.height];
  }
} else if (engine === 'avoid') {
  const { AvoidLib } = require('libavoid-js');
  await AvoidLib.load();
  const A = AvoidLib.getInstance();
  const router = new A.Router(A.OrthogonalRouting);
  router.setRoutingParameter(A.shapeBufferDistance, 8);
  router.setRoutingParameter(A.idealNudgingDistance, 10);
  router.setRoutingParameter(A.segmentPenalty, 50);
  router.setRoutingParameter(A.crossingPenalty, 200);
  router.setRoutingOption(A.nudgeOrthogonalSegmentsConnectedToShapes, true);
  router.setRoutingOption(A.nudgeSharedPathsWithCommonEndPoint, true);
  router.setRoutingOption(A.performUnifyingNudgingPreprocessingStep, true);
  const shapes = {};
  for (const n of job.nodes) {
    shapes[n.id] = { ref: new A.ShapeRef(router, new A.Rectangle(new A.Point(n.x, n.y), new A.Point(n.x + n.w, n.y + n.h))), n, pin: 1 };
    out.nodes[n.id] = [n.x, n.y, n.w, n.h];
  }
  const DIR = { top: A.ConnDirUp, bottom: A.ConnDirDown, left: A.ConnDirLeft, right: A.ConnDirRight };
  const end = (p) => {
    const s = shapes[p.id];
    const id = s.pin++;
    // proportional pin position on the box, visible only in the side's direction
    new A.ShapeConnectionPin(s.ref, id, (p.x - s.n.x) / s.n.w, (p.y - s.n.y) / s.n.h, true, 0, DIR[p.side]);
    return new A.ConnEnd(s.ref, id);
  };
  const conns = job.edges.map((e) => {
    const c = new A.ConnRef(router, end(e.src), end(e.dst));
    c.setHateCrossings(true);
    return [e.k, c];
  });
  router.processTransaction();
  for (const [k, c] of conns) {
    const r = c.displayRoute();
    const pts = [];
    for (let i = 0; i < r.size(); i++) pts.push([r.get_ps(i).x, r.get_ps(i).y]);
    out.edges[k] = pts;
  }
} else {
  throw new Error('engine: elk | avoid');
}
process.stdout.write(JSON.stringify(out));
