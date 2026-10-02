/* Charts for site/pages/cgm-remote-monitor-15.0.9-colophon.html, inlined by
 * tools/site/render_colophon.py. Reads the JSON in #colophon-data and draws
 * into every [data-chart] element. Plain SVG, no library. Every value drawn
 * here is also in the table under its chart, so the tooltip never gates. */
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("colophon-data").textContent);
  var NS = "http://www.w3.org/2000/svg";
  var ORIGINS = [
    ["latent", "found by audit, lab or survey", "--s1"],
    ["github", "from GitHub issues", "--s2"],
    ["connector", "in the CGM connector", "--s3"],
    ["review", "in review before merge", "--s4"],
    ["escaped", "introduced by a fix (regression)", "--s5"]
  ];
  var tip = document.createElement("div");
  tip.className = "viz-tip";
  tip.setAttribute("role", "status");
  document.body.appendChild(tip);

  function el(name, attrs, parent) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function text(parent, x, y, s, cls, anchor) {
    var t = el("text", { x: x, y: y, "class": cls || "ax", "text-anchor": anchor || "middle" }, parent);
    t.textContent = s;
    return t;
  }
  function day(s) { return s.slice(5).replace("-", "/"); }
  function fmt(n) { return n.toLocaleString("en-US"); }
  /* a round tick step giving about four intervals, and the axis top on that step */
  function niceStep(v) {
    var raw = Math.max(v, 1) / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), steps = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * p >= raw) return Math.max(1, steps[i] * p);
    return 10 * p;
  }
  function niceMax(v) { var st = niceStep(v); return Math.ceil(Math.max(v, 1) / st) * st; }
  function ticks(max) {
    var st = niceStep(max), out = [];
    if (max / st > 6) st = max / 4;
    for (var t = 0; t <= max + 1e-9; t += st) out.push(Math.round(t));
    return out;
  }
  /* tooltip: rows = [[value, label, colorVar or null, shape]] */
  function show(evt, title, rows) {
    while (tip.firstChild) tip.removeChild(tip.firstChild);
    var h = document.createElement("div"); h.className = "viz-tip-h"; h.textContent = title; tip.appendChild(h);
    rows.forEach(function (r) {
      var row = document.createElement("div"); row.className = "viz-tip-r";
      if (r[2]) { var k = document.createElement("span"); k.className = "viz-key"; k.style.background = "var(" + r[2] + ")"; row.appendChild(k); }
      var v = document.createElement("strong"); v.textContent = r[0]; row.appendChild(v);
      var l = document.createElement("span"); l.textContent = " " + r[1]; row.appendChild(l);
      tip.appendChild(row);
    });
    tip.style.display = "block";
    var bx = evt.target.getBoundingClientRect ? evt.target.getBoundingClientRect() : null;
    var x = evt.clientX != null && evt.clientX !== 0 ? evt.clientX : (bx ? bx.left + bx.width / 2 : 0);
    var y = evt.clientY != null && evt.clientY !== 0 ? evt.clientY : (bx ? bx.top : 0);
    var w = tip.offsetWidth, vw = document.documentElement.clientWidth;
    tip.style.left = Math.max(8, Math.min(vw - w - 8, x + 14)) + "px";
    tip.style.top = (y + window.scrollY - tip.offsetHeight - 12) + "px";
  }
  function hide() { tip.style.display = "none"; }
  function hit(node, title, rows) {
    node.setAttribute("tabindex", "0");
    node.setAttribute("aria-label", title + ": " + rows.map(function (r) { return r[0] + " " + r[1]; }).join(", "));
    node.addEventListener("pointermove", function (e) { show(e, title, rows); });
    node.addEventListener("pointerleave", hide);
    node.addEventListener("focus", function (e) { show(e, title, rows); });
    node.addEventListener("blur", hide);
  }
  function frame(host, height, left) {
    while (host.firstChild) host.removeChild(host.firstChild);
    var W = Math.max(300, host.clientWidth), m = { t: 18, r: 16, b: 34, l: left || 40 };
    var svg = el("svg", { width: W, height: height, viewBox: "0 0 " + W + " " + height, role: "img",
      "aria-label": host.getAttribute("aria-label") || "" }, host);
    return { svg: svg, W: W, H: height, m: m, iw: W - m.l - m.r, ih: height - m.t - m.b };
  }
  function yAxis(f, max, label) {
    ticks(max).forEach(function (v) {
      var y = f.m.t + f.ih - (v / max) * f.ih;
      el("line", { x1: f.m.l, x2: f.m.l + f.iw, y1: y, y2: y, "class": v === 0 ? "base" : "grid" }, f.svg);
      text(f.svg, f.m.l - 6, y + 4, fmt(v), "ax", "end");
    });
    if (label) text(f.svg, f.m.l, f.m.t - 6, label, "ax", "start");
  }
  function xDays(f, dates, xOf, every) {
    dates.forEach(function (d, i) {
      if (i % every !== 0 && i !== dates.length - 1) return;
      text(f.svg, xOf(i), f.m.t + f.ih + 16, day(d), "ax");
    });
  }

  /* columns, optionally stacked; series = [[key, label, colorVar, values[]]] */
  function columns(host, dates, series, opts) {
    var f = frame(host, opts.height || 240);
    var tot = dates.map(function (_, i) { return series.reduce(function (s, se) { return s + se[3][i]; }, 0); });
    var max = niceMax(Math.max.apply(null, tot));
    yAxis(f, max, opts.yLabel);
    var band = f.iw / dates.length, bw = Math.min(24, Math.max(3, band - 4));
    var xOf = function (i) { return f.m.l + band * i + band / 2; };
    var yOf = function (v) { return f.m.t + f.ih - (v / max) * f.ih; };
    dates.forEach(function (d, i) {
      var acc = 0, segs = series.filter(function (se) { return se[3][i] > 0; });
      segs.forEach(function (se, j) {
        var v = se[3][i], y0 = yOf(acc), y1 = yOf(acc + v), top = j === segs.length - 1;
        var h = Math.max(1, y0 - y1 - (j > 0 ? 2 : 0));
        var x = xOf(i) - bw / 2, y = y1;
        var path = top
          ? "M" + x + "," + (y + h) + "V" + (y + 4) + "Q" + x + "," + y + " " + (x + 4) + "," + y + "H" + (x + bw - 4) + "Q" + (x + bw) + "," + y + " " + (x + bw) + "," + (y + 4) + "V" + (y + h) + "Z"
          : "M" + x + "," + (y + h) + "V" + y + "H" + (x + bw) + "V" + (y + h) + "Z";
        el("path", { d: path, style: "fill:var(" + se[2] + ")", "class": "mark" }, f.svg);
        acc += v;
      });
      var hitbox = el("rect", { x: f.m.l + band * i, y: f.m.t, width: band, height: f.ih, "class": "hit" }, f.svg);
      var rows = series.filter(function (se) { return se[3][i] > 0; }).map(function (se) { return [fmt(se[3][i]), se[1], se[2]]; });
      if (!rows.length) rows = [["0", opts.unit || ""]];
      if (opts.extra) rows = rows.concat(opts.extra(i));
      hit(hitbox, d, rows);
    });
    if (opts.marks) opts.marks.forEach(function (mk, n) {
      var i = dates.indexOf(mk.date); if (i < 0) return;
      var y = f.m.t + f.ih + 22;
      el("circle", { cx: xOf(i), cy: y + 6, r: 7, "class": "pin" }, f.svg);
      text(f.svg, xOf(i), y + 10, String(n + 1), "pin-n");
    });
    xDays(f, dates, xOf, opts.every || Math.ceil(dates.length / 8));
    if (opts.marks) { f.svg.setAttribute("height", f.H + 18); f.svg.setAttribute("viewBox", "0 0 " + f.W + " " + (f.H + 18)); }
  }

  /* lines over an index axis; series = [[label, colorVar, values[]]] */
  function lines(host, xs, xLabel, series, opts) {
    var f = frame(host, opts.height || 260, 48);
    f.m.r = opts.endLabels ? 120 : 16; f.iw = f.W - f.m.l - f.m.r;
    var all = []; series.forEach(function (s) { all = all.concat(s[2].filter(function (v) { return v != null; })); });
    if (opts.ref) all.push(opts.ref.value);
    var max = niceMax(Math.max.apply(null, all));
    yAxis(f, max, opts.yLabel);
    var n = xs.length, xOf = function (i) { return f.m.l + (n === 1 ? f.iw / 2 : (f.iw * i) / (n - 1)); };
    var yOf = function (v) { return f.m.t + f.ih - (v / max) * f.ih; };
    if (opts.ref) {
      var ry = yOf(opts.ref.value);
      el("line", { x1: f.m.l, x2: f.m.l + f.iw, y1: ry, y2: ry, "class": "ref" }, f.svg);
      text(f.svg, f.m.l + 6, ry - 6, opts.ref.label, "lab", "start");
    }
    series.forEach(function (s) {
      var d = "", started = false;
      s[2].forEach(function (v, i) { if (v == null) return; d += (started ? "L" : "M") + xOf(i) + "," + yOf(v); started = true; });
      el("path", { d: d, "class": "line", style: "stroke:var(" + s[1] + ")" }, f.svg);
      if (opts.markers) s[2].forEach(function (v, i) {
        if (v == null) return;
        var hollow = opts.hollow && opts.hollow(i);
        el("circle", { cx: xOf(i), cy: yOf(v), r: 4, "class": hollow ? "dot hollow" : "dot", style: (hollow ? "stroke:" : "fill:") + "var(" + s[1] + ")" }, f.svg);
      });
      if (opts.endLabels) {
        var last = s[2].length - 1; while (last >= 0 && s[2][last] == null) last--;
        text(f.svg, xOf(last) + 8, yOf(s[2][last]) + 4, fmt(s[2][last]) + " " + s[0], "lab", "start");
      }
    });
    xLabel.forEach(function (lab, i) { if (lab) text(f.svg, xOf(i), f.m.t + f.ih + 16, lab, "ax"); });
    var cross = el("line", { x1: 0, x2: 0, y1: f.m.t, y2: f.m.t + f.ih, "class": "cross" }, f.svg);
    xs.forEach(function (x, i) {
      var w = n === 1 ? f.iw : f.iw / (n - 1);
      var r = el("rect", { x: xOf(i) - w / 2, y: f.m.t, width: w, height: f.ih, "class": "hit" }, f.svg);
      var rows = series.filter(function (s) { return s[2][i] != null; }).map(function (s) { return [fmt(s[2][i]), s[0], s[1]]; });
      if (opts.extra) rows = rows.concat(opts.extra(i));
      hit(r, opts.title ? opts.title(i) : x, rows);
      r.addEventListener("pointermove", function () { cross.setAttribute("x1", xOf(i)); cross.setAttribute("x2", xOf(i)); cross.style.opacity = 1; });
      r.addEventListener("pointerleave", function () { cross.style.opacity = 0; });
    });
  }

  /* one row per regression: caused -> filed -> fixed on a date axis */
  function dotRange(host, rows) {
    var rowH = 30, f = frame(host, rows.length * rowH + 52, 64);
    var ds = []; rows.forEach(function (r) { ds.push(r.caused, r.filed, r.fixed); });
    ds.sort();
    var t0 = Date.parse(ds[0]) - 864e5, t1 = Date.parse(ds[ds.length - 1]) + 864e5;
    var xOf = function (d) { return f.m.l + ((Date.parse(d) - t0) / (t1 - t0)) * f.iw; };
    for (var t = t0; t <= t1; t += 864e5) {
      var x = f.m.l + ((t - t0) / (t1 - t0)) * f.iw, iso = new Date(t).toISOString().slice(0, 10);
      el("line", { x1: x, x2: x, y1: f.m.t, y2: f.m.t + rows.length * rowH, "class": "grid" }, f.svg);
      if (((t - t0) / 864e5) % 2 === 1) text(f.svg, x, f.m.t + rows.length * rowH + 16, day(iso), "ax");
    }
    var KEYS = [["caused", "cause merged", "--s1"], ["filed", "found and filed", "--s2"], ["fixed", "fix merged", "--s3"]];
    rows.forEach(function (r, i) {
      var y = f.m.t + rowH * i + rowH / 2;
      text(f.svg, f.m.l - 8, y + 4, r.id, "lab", "end");
      el("line", { x1: xOf(r.caused), x2: xOf(r.fixed), y1: y, y2: y, "class": "span" }, f.svg);
      var seen = {};
      KEYS.forEach(function (k) {
        var d = r[k[0]], off = (seen[d] = (seen[d] || 0) + 1) - 1;
        var same = KEYS.filter(function (q) { return r[q[0]] === d; }).length;
        var cx = xOf(d) + (off - (same - 1) / 2) * 11;
        el("circle", { cx: cx, cy: y, r: 5, "class": "dot", style: "fill:var(" + k[2] + ")" }, f.svg);
      });
      var hb = el("rect", { x: f.m.l, y: y - rowH / 2, width: f.iw, height: rowH, "class": "hit" }, f.svg);
      hit(hb, r.id + " — " + r.family, [
        [day(r.caused), "cause merged (#" + r.cause_pr + ")", "--s1"],
        [day(r.filed), "found and filed", "--s2"],
        [day(r.fixed), "fix merged (#" + r.fix_pr + ")", "--s3"]]);
    });
  }

  /* horizontal bars, one per category; emphasised rows in the accent, the rest recessive */
  function hbars(host, rows) {
    var rowH = 46;
    var f = frame(host, rows.length * rowH + 30, 8);
    f.m.r = 40; f.iw = f.W - f.m.l - f.m.r;
    var max = niceMax(Math.max.apply(null, rows.map(function (r) { return r.value; })));
    ticks(max).forEach(function (v) {
      var x = f.m.l + (v / max) * f.iw;
      el("line", { x1: x, x2: x, y1: f.m.t, y2: f.m.t + rows.length * rowH, "class": v === 0 ? "base" : "grid" }, f.svg);
      text(f.svg, x, f.m.t + rows.length * rowH + 16, fmt(v), "ax");
    });
    rows.forEach(function (r, i) {
      var top = f.m.t + rowH * i, y = top + 22, w = Math.max(4, (r.value / max) * f.iw), x0 = f.m.l;
      text(f.svg, x0, top + 14, r.label, "lab", "start");
      var path = "M" + x0 + "," + y + "H" + (x0 + w - 4) + "Q" + (x0 + w) + "," + y + " " + (x0 + w) + "," + (y + 4) +
        "V" + (y + 14) + "Q" + (x0 + w) + "," + (y + 18) + " " + (x0 + w - 4) + "," + (y + 18) + "H" + x0 + "Z";
      el("path", { d: path, "class": "mark", style: "fill:var(" + (r.emph ? "--s1" : "--vmute") + ")" }, f.svg);
      text(f.svg, x0 + w + 6, y + 13, fmt(r.value), "lab", "start");
      var hb = el("rect", { x: 0, y: top, width: f.W, height: rowH, "class": "hit" }, f.svg);
      hit(hb, r.label, [[fmt(r.value), "entries"], ["", r.ids.join(", ")]]);
    });
  }

  var D = DATA;
  var draw = {
    merges: function (h) {
      var m = D.merges_per_day;
      columns(h, m.map(function (x) { return x.date; }), [["merges", "PRs merged", "--s1", m.map(function (x) { return x.count; })]],
        { yLabel: "PRs merged", unit: "PRs merged", every: 7,
          extra: function (i) { return m[i].prs.length ? [["", "#" + m[i].prs.join(", #")]] : []; } });
    },
    arrival: function (h) {
      var dd = D.defects;
      columns(h, dd.map(function (x) { return x.date; }),
        ORIGINS.map(function (o) { return [o[0], o[1], o[2], dd.map(function (x) { return x.filed[o[0]]; })]; }),
        { yLabel: "register entries filed", unit: "filed", every: 3, height: 250, marks: D.checks });
    },
    burnup: function (h) {
      var dd = D.defects;
      lines(h, dd.map(function (x) { return x.date; }), dd.map(function (x, i) { return i % 3 === 0 || i === dd.length - 1 ? day(x.date) : ""; }),
        [["filed", "--s1", dd.map(function (x) { return x.filed_cum; })], ["closed", "--s3", dd.map(function (x) { return x.closed_cum; })]],
        { yLabel: "register entries in 15.0.9's scope, running total", endLabels: true,
          extra: function (i) { return [[fmt(dd[i].filed_cum - dd[i].closed_cum), "open"]]; } });
    },
    tests: function (h) {
      var r = D.runs;
      lines(h, r.map(function (x) { return x.label; }),
        r.map(function (x, i) { return i === 0 || i === r.length - 1 || x.label === "run 020" || x.label === "run 010" ? x.label.replace("run ", "") : ""; }),
        [["passing", "--s1", r.map(function (x) { return x.passing; })]],
        { yLabel: "tests passing", markers: true, ref: { value: D.kpis.passing.base, label: "15.0.8: " + fmt(D.kpis.passing.base) },
          hollow: function (i) { return r[i].cells == null || r[i].cells < 6; },
          title: function (i) { return r[i].label + " (" + day(r[i].date) + ")"; },
          extra: function (i) { return [["", r[i].kind + (r[i].cells ? ", " + r[i].cells + (r[i].cells === 1 ? " cell" : " cells") : "")]]; } });
    },
    regressions: function (h) { dotRange(h, D.regressions); },
    open: function (h) {
      var EMPH = /waiting on a maintainer decision|no decision/;
      hbars(h, D.open_entries.map(function (o) { return { label: o.disposition, value: o.count, ids: o.ids, emph: EMPH.test(o.disposition) }; }));
    }
  };
  function render() {
    document.querySelectorAll("[data-chart]").forEach(function (h) { var k = h.getAttribute("data-chart"); if (draw[k]) draw[k](h); });
  }
  render();
  var w = document.documentElement.clientWidth;
  window.addEventListener("resize", function () {
    if (document.documentElement.clientWidth === w) return;
    w = document.documentElement.clientWidth; hide(); render();
  });
  if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
})();
