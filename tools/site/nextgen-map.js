/* Interactive dependency map for site/pages/nightscout-next-gen-platform.html,
 * inlined by tools/site/render_nextgen.py. Reads the JSON in #nextgen-data and
 * draws into [data-chart="map"]. Plain SVG, no library. Every item drawn here
 * is also in the table under the map, so nothing depends on the script.
 *
 * Columns are phases, rows are tracks. Selecting an item highlights what it
 * depends on and what depends on it; selecting a decision highlights the items
 * it holds up. */
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("nextgen-data").textContent);
  var NS = "http://www.w3.org/2000/svg";
  var host = document.querySelector('[data-chart="map"]');
  var panel = document.getElementById("map-detail");
  if (!host) return;

  var tracks = DATA.tracks, phases = DATA.phases, items = DATA.items;
  var byId = {};
  items.forEach(function (it) { byId[it.id] = it; });
  var STATE = {};
  DATA.states.forEach(function (s) { STATE[s.id] = s; });

  var COLW = 196, ROWH = 112, NODEW = 172, NODEH = 62, PADL = 112, PADT = 34, GAPY = 8;
  // stack items that share a cell
  var cells = {};
  items.forEach(function (it) {
    var k = it.phase + "|" + it.track;
    (cells[k] = cells[k] || []).push(it);
  });
  var rowH = {};
  tracks.forEach(function (t) {
    var most = 1;
    phases.forEach(function (p) { most = Math.max(most, (cells[p.id + "|" + t.id] || []).length); });
    rowH[t.id] = Math.max(ROWH, most * (NODEH + GAPY) + 24);
  });
  var rowY = {}, y = PADT;
  tracks.forEach(function (t) { rowY[t.id] = y; y += rowH[t.id]; });
  var W = PADL + phases.length * COLW, H = y + 8;
  var pos = {};
  Object.keys(cells).forEach(function (k) {
    var parts = k.split("|"), pi = phases.findIndex(function (p) { return p.id === parts[0]; });
    var list = cells[k], top = rowY[parts[1]] + (rowH[parts[1]] - list.length * (NODEH + GAPY) + GAPY) / 2;
    list.forEach(function (it, i) {
      pos[it.id] = { x: PADL + pi * COLW + (COLW - NODEW) / 2, y: top + i * (NODEH + GAPY) };
    });
  });

  function el(name, attrs, parent) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function txt(parent, x, yy, s, cls, anchor) {
    var t = el("text", { x: x, y: yy, "class": cls, "text-anchor": anchor || "start" }, parent);
    t.textContent = s;
    return t;
  }
  function clip(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }

  var scroller = document.createElement("div");
  scroller.className = "map-scroll";
  host.appendChild(scroller);
  var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, style: "max-width:none", role: "img",
    "aria-label": "Dependency map of " + items.length + " work items across " + tracks.length + " tracks" }, scroller);

  // phase headers and row bands
  phases.forEach(function (p, i) {
    txt(svg, PADL + i * COLW + COLW / 2, 18, p.label, "ax", "middle");
    if (i) el("line", { x1: PADL + i * COLW, x2: PADL + i * COLW, y1: PADT - 6, y2: H - 4, "class": "grid" }, svg);
  });
  tracks.forEach(function (t, i) {
    el("rect", { x: 0, y: rowY[t.id], width: W, height: rowH[t.id], "class": i % 2 ? "band b1" : "band" }, svg);
    el("rect", { x: 8, y: rowY[t.id] + 12, width: 4, height: rowH[t.id] - 24, rx: 2, fill: "var(" + t.color + ")" }, svg);
    var lab = txt(svg, 20, rowY[t.id] + rowH[t.id] / 2 - 4, t.label, "lab");
    lab.setAttribute("font-weight", "600");
    txt(svg, 20, rowY[t.id] + rowH[t.id] / 2 + 12, t.sub || "", "ax");
  });

  // edges
  var edgeLayer = el("g", {}, svg), edges = [];
  items.forEach(function (it) {
    (it.depends || []).forEach(function (dep) {
      if (!pos[dep]) return;
      var a = pos[dep], b = pos[it.id];
      var x1 = a.x + NODEW, y1 = a.y + NODEH / 2, x2 = b.x, y2 = b.y + NODEH / 2;
      if (x2 <= x1) { x1 = a.x + NODEW / 2; y1 = a.y + (b.y > a.y ? NODEH : 0); x2 = b.x + NODEW / 2; y2 = b.y + (b.y > a.y ? 0 : NODEH); }
      var mx = (x1 + x2) / 2;
      var d = x2 > x1 + 10 ? "M" + x1 + "," + y1 + " C" + mx + "," + y1 + " " + mx + "," + y2 + " " + x2 + "," + y2
        : "M" + x1 + "," + y1 + " L" + x2 + "," + y2;
      edges.push({ from: dep, to: it.id, node: el("path", { d: d, "class": "edge", "marker-end": "url(#arrow)" }, edgeLayer) });
    });
  });
  var defs = el("defs", {}, svg);
  var mk = el("marker", { id: "arrow", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
  el("path", { d: "M0,0 L8,4 L0,8 z", "class": "arrowhead" }, mk);

  // nodes
  var nodes = {};
  items.forEach(function (it) {
    var p = pos[it.id], st = STATE[it.state] || { label: it.state, style: "planned" };
    var trk = tracks.find(function (t) { return t.id === it.track; });
    var g = el("g", { "class": "node st-" + st.style, tabindex: 0, role: "button",
      "aria-label": it.id + ": " + it.title + ", " + st.label }, svg);
    el("rect", { x: p.x, y: p.y, width: NODEW, height: NODEH, rx: 6, "class": "box", style: "--c:var(" + trk.color + ")" }, g);
    el("rect", { x: p.x, y: p.y, width: 4, height: NODEH, rx: 2, fill: "var(" + trk.color + ")" }, g);
    txt(g, p.x + 12, p.y + 18, clip(it.id, 22), "nid");
    txt(g, p.x + 12, p.y + 35, clip(it.short || it.title, 26), "ntl");
    txt(g, p.x + 12, p.y + 52, st.mark + " " + st.label, "nst");
    g.addEventListener("click", function () { select(it.id); });
    g.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(it.id); } });
    nodes[it.id] = g;
  });

  function closure(id, dir) {
    var seen = {}, stack = [id];
    while (stack.length) {
      var cur = stack.pop();
      edges.forEach(function (e) {
        var nxt = dir === "up" ? (e.to === cur ? e.from : null) : (e.from === cur ? e.to : null);
        if (nxt && !seen[nxt]) { seen[nxt] = true; stack.push(nxt); }
      });
    }
    return seen;
  }
  function clear() {
    svg.classList.remove("focus");
    Object.keys(nodes).forEach(function (k) { nodes[k].classList.remove("on", "up", "down", "held"); });
    edges.forEach(function (e) { e.node.classList.remove("on"); });
    document.querySelectorAll(".dcard").forEach(function (c) { c.classList.remove("on"); });
  }
  function link(href, label) { return href ? '<a href="' + href + '">' + label + "</a>" : label; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function select(id) {
    clear();
    var it = byId[id];
    var up = closure(id, "up"), down = closure(id, "down");
    svg.classList.add("focus");
    nodes[id].classList.add("on");
    Object.keys(up).forEach(function (k) { nodes[k] && nodes[k].classList.add("up"); });
    Object.keys(down).forEach(function (k) { nodes[k] && nodes[k].classList.add("down"); });
    edges.forEach(function (e) {
      if ((e.to === id || up[e.to]) && (up[e.from] || e.from === id) || (e.from === id || down[e.from]) && (down[e.to] || e.to === id)) e.node.classList.add("on");
    });
    var st = STATE[it.state] || { label: it.state };
    var held = DATA.decisions.filter(function (d) { return (d.holds || []).indexOf(id) > -1; });
    panel.innerHTML =
      '<div class="dh"><strong>' + esc(it.id) + "</strong> · " + esc(st.label) + "</div>" +
      "<p>" + esc(it.title) + "</p>" +
      '<dl class="dl">' +
      (it.where ? "<dt>Where</dt><dd>" + esc(it.where) + "</dd>" : "") +
      (it.ref ? "<dt>Branch or PR</dt><dd>" + link(it.ref_href, esc(it.ref)) + "</dd>" : "") +
      (it.check ? "<dt>Checked by</dt><dd>" + esc(it.check) + "</dd>" : "") +
      (it.depends && it.depends.length ? "<dt>Needs</dt><dd>" + it.depends.map(esc).join(", ") + "</dd>" : "") +
      (held.length ? "<dt>Waiting on</dt><dd>" + held.map(function (d) { return esc(d.id + " " + d.short); }).join("; ") + "</dd>" : "") +
      (it.spec ? "<dt>Specified in</dt><dd>" + it.spec.map(function (s) { return link(s.href, esc(s.label)); }).join(", ") + "</dd>" : "") +
      "</dl>";
    panel.hidden = false;
  }
  function selectDecision(did) {
    clear();
    var d = DATA.decisions.find(function (x) { return x.id === did; });
    svg.classList.add("focus");
    (d.holds || []).forEach(function (k) {
      if (!nodes[k]) return;
      nodes[k].classList.add("held");
      Object.keys(closure(k, "down")).forEach(function (j) { nodes[j] && nodes[j].classList.add("down"); });
    });
    var card = document.getElementById("d-" + did);
    if (card) card.classList.add("on");
    panel.innerHTML = '<div class="dh"><strong>' + esc(d.id) + "</strong> · decision</div><p>" + esc(d.question) +
      "</p><p class=\"mut\">Holds up " + (d.holds || []).map(esc).join(", ") + ", and everything after them (outlined).</p>";
    panel.hidden = false;
  }
  svg.addEventListener("click", function (e) { if (e.target === svg || e.target.classList.contains("band")) { clear(); panel.hidden = true; } });

  // track filter chips
  var bar = document.getElementById("map-filter");
  if (bar) {
    var active = {};
    tracks.forEach(function (t) {
      active[t.id] = true;
      var b = document.createElement("button");
      b.type = "button"; b.className = "chip on"; b.setAttribute("aria-pressed", "true");
      b.innerHTML = '<span class="sw" style="background:var(' + t.color + ')"></span>' + esc(t.label);
      b.addEventListener("click", function () {
        active[t.id] = !active[t.id];
        b.classList.toggle("on", active[t.id]); b.setAttribute("aria-pressed", String(active[t.id]));
        items.forEach(function (it) { nodes[it.id].classList.toggle("dim", !active[it.track]); });
        edges.forEach(function (e) { e.node.classList.toggle("dim", !(active[byId[e.from].track] && active[byId[e.to].track])); });
      });
      bar.appendChild(b);
    });
  }
  document.querySelectorAll("[data-decision]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      selectDecision(btn.getAttribute("data-decision"));
      host.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
})();
