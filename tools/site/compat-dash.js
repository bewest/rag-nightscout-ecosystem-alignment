/* Charts and tables of site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html.
 * Inlined by tools/site/render_compat.py. The page's data sits in
 * <script type="application/json" id="compat-data-NAME"> blocks; `dash` below is
 * a small stand-in for the dashboard host the page was first drawn in:
 *   dash.data(id)       -> {status: 'ok' | 'missing' | 'error', data}
 *   dash.draw(name, fn) registers fn and runs it on each [data-draw=name];
 *                       dash.draw(name) re-runs it. Every drawing re-runs when
 *                       the page width or the colour scheme changes.
 *   dash.colors         the categorical chart colours, read from --cds-chart-1..3
 * d3 v7 is loaded before this script. */
(function () {
  var cache = {}, fns = {}, order = [];
  function data(id) {
    if (!cache[id]) {
      var el = document.getElementById('compat-data-' + id);
      if (!el) cache[id] = { status: 'missing', data: null };
      else { try { cache[id] = { status: 'ok', data: JSON.parse(el.textContent) }; } catch (e) { cache[id] = { status: 'error', data: null }; } }
    }
    return cache[id];
  }
  function run(name) {
    var f = fns[name]; if (!f) return;
    document.querySelectorAll('[data-draw="' + name + '"]').forEach(function (el) { f(el); });
  }
  function draw(name, fn) {
    if (fn) { if (!fns[name]) order.push(name); fns[name] = fn; }
    run(name);
  }
  function redrawAll() { order.forEach(run); }
  var dash = { data: data, draw: draw };
  Object.defineProperty(dash, 'colors', {
    get: function () {
      var cs = getComputedStyle(document.documentElement);
      return [1, 2, 3].map(function (i) { return cs.getPropertyValue('--cds-chart-' + i).trim(); });
    }
  });
  var lastW = window.innerWidth, timer = null;
  window.addEventListener('resize', function () {
    if (window.innerWidth === lastW) return;
    lastW = window.innerWidth;
    clearTimeout(timer); timer = setTimeout(redrawAll, 150);
  });
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    if (mq.addEventListener) mq.addEventListener('change', redrawAll);
  }
  window.dash = dash;
})();


(function () {
  var fmt = d3.format(',');
  var COL = ['activity', 'devicestatus', 'entries', 'food', 'profile', 'settings', 'treatments'];
  var PATHS = ['v1', 'inproc', 'v3', 'ws'];
  var VCLASS = { 'Defect': 'defect', 'Bug fix': 'fix', 'No value change': 'none', 'Decided': '' };
  var originColor = function (i) { return dash.colors[i]; };
  window.cwState = { tSort: 'score', tDir: -1, cellGroup: '', cellHeat: null };

  function rows(id) { var r = dash.data(id); return r.status === 'ok' ? r.data : null; }
  function headline(metric) {
    var r = rows('headline'); if (!r) return null;
    var row = r.find(function (x) { return x.metric === metric; });
    return row ? row.value : null;
  }
  function origins() {
    return headline('origin_labels') || { '8879': '#8879 only', dev: 'already on dev', both: 'dev, then #8879' };
  }
  function fillNumber(name, metric) {
    dash.draw(name, function (el) { var v = headline(metric); el.textContent = v === null ? '—' : fmt(v); });
  }
  [['h-cells', 'cells'], ['h-differ', 'differ'], ['h-defect', 'defect_cells'], ['t-differ', 'differ'], ['t-8879', 'by_8879'], ['t-dev', 'on_dev'], ['t-both', 'both'], ['t-format', 'format_cells'], ['t-defect', 'defect_cells'], ['t-unexp', 'unexplained']]
    .forEach(function (p) { fillNumber(p[0], p[1]); });
  dash.draw('sw0', function (el) { el.style.background = originColor(0); });
  dash.draw('sw1', function (el) { el.style.background = originColor(1); });
  dash.draw('sw2', function (el) { el.style.background = originColor(2); });
  dash.draw('sw-measured', function (el) { el.style.background = 'var(--color-ok)'; });
  dash.draw('sw-read', function (el) { el.style.background = 'var(--color-warn)'; });

  function tooltip(box) {
    var t = box.querySelector('.tip');
    if (!t) { t = document.createElement('div'); t.className = 'tip'; t.hidden = true; box.appendChild(t); }
    return {
      show: function (ev, lines) {
        t.replaceChildren();
        lines.forEach(function (l, i) { var d = document.createElement('div'); if (i === 0) d.className = 'k'; d.textContent = l; t.appendChild(d); });
        t.hidden = false;
        var b = box.getBoundingClientRect(), x = ev.clientX - b.left + 12, y = ev.clientY - b.top + 12;
        var w = t.offsetWidth, h = t.offsetHeight;
        if (x + w > box.clientWidth) x = Math.max(0, ev.clientX - b.left - w - 12);
        if (y + h > box.clientHeight) y = Math.max(0, ev.clientY - b.top - h - 12);
        t.style.left = x + 'px'; t.style.top = y + 'px';
      },
      hide: function () { t.hidden = true; }
    };
  }

  // Families: horizontal stacked bars by origin
  dash.draw('families', function (el) {
    var r = rows('families');
    el.replaceChildren();
    if (!r) { el.textContent = '—'; return; }
    var fams = d3.rollups(r, function (v) { return d3.sum(v, function (d) { return d.cells; }); }, function (d) { return d.family; })
      .sort(function (a, b) { return b[1] - a[1]; }).map(function (d) { return d[0]; });
    var labels = origins(), origins = ['8879', 'dev', 'both'];
    var W = el.clientWidth || 600, rowH = 34, H = fams.length * rowH + 28;
    var svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', '0 0 ' + W + ' ' + H);
    var probe = svg.append('text').attr('font-size', 12);
    var lw = d3.max(fams, function (f) { probe.text(f); return probe.node().getComputedTextLength(); }) + 12;
    probe.remove();
    var totals = {}; fams.forEach(function (f) { totals[f] = d3.sum(r.filter(function (d) { return d.family === f; }), function (d) { return d.cells; }); });
    var x = d3.scaleLinear([0, d3.max(Object.values(totals))], [lw, W - 56]);
    var y = d3.scaleBand(fams, [0, fams.length * rowH]).padding(0.28);
    var tip = tooltip(el);
    svg.append('g').selectAll('line').data(x.ticks(5)).join('line')
      .attr('x1', x).attr('x2', x).attr('y1', 0).attr('y2', fams.length * rowH).attr('stroke', 'var(--cds-chart-grid)');
    svg.append('g').attr('transform', 'translate(0,' + (fams.length * rowH + 4) + ')').selectAll('text').data(x.ticks(5)).join('text')
      .attr('x', x).attr('y', 12).attr('text-anchor', 'middle').attr('font-size', 11).text(d3.format(','));
    fams.forEach(function (f) {
      var acc = 0;
      origins.forEach(function (o, i) {
        var row = r.find(function (d) { return d.family === f && d.origin === o; }); if (!row) return;
        svg.append('rect').attr('x', x(acc)).attr('y', y(f)).attr('width', Math.max(1, x(acc + row.cells) - x(acc))).attr('height', y.bandwidth())
          .attr('fill', originColor(i)).attr('rx', 2)
          .on('mousemove', function (ev) { tip.show(ev, [f, labels[o] + ': ' + fmt(row.cells) + ' cells']); }).on('mouseleave', tip.hide);
        acc += row.cells;
      });
      svg.append('text').attr('x', 0).attr('y', y(f) + y.bandwidth() / 2).attr('dy', '0.35em').attr('font-size', 12).style('fill', 'var(--color-fg)').text(f);
      svg.append('text').attr('x', x(totals[f]) + 6).attr('y', y(f) + y.bandwidth() / 2).attr('dy', '0.35em').attr('font-size', 12).text(fmt(totals[f]));
    });
  });

  function chip(text, cls) { var s = document.createElement('span'); s.className = 'chip ' + (cls || ''); s.textContent = text; return s; }
  function td(content, cls) {
    var c = document.createElement('td'); if (cls) c.className = cls;
    if (content instanceof Node) c.appendChild(content); else c.textContent = content;
    return c;
  }

  // Reconsider cards that name a group: <a href="#reconsider-ID">LETTER: HEAD</a>, one per card.
  // The cards are rendered in the page; each carries data-groups, data-letter and data-head.
  function restoreLinks(group) {
    var box = document.createElement('span'); box.className = 'restore-links';
    document.querySelectorAll('.rc-card').forEach(function (card) {
      if ((card.getAttribute('data-groups') || '').split(' ').indexOf(group) === -1) return;
      var a = document.createElement('a'); a.href = '#' + card.id;
      a.textContent = card.getAttribute('data-letter') + ': ' + card.getAttribute('data-head');
      a.className = 'chip ' + (card.classList.contains('keep') ? 'none' : 'cand');
      box.appendChild(a);
    });
    if (!box.childNodes.length) box.textContent = '—';
    return box;
  }

  // Groups table
  dash.draw('groups-body', function (el) {
    var r = rows('groups'); el.replaceChildren(); if (!r) return;
    var max = d3.max(r, function (d) { return d.cells; });
    r.forEach(function (g) {
      var tr = document.createElement('tr'); tr.dataset.key = g.group;
      tr.appendChild(td(chip(g.verdict, VCLASS[g.verdict])));
      tr.appendChild(td(g.name));
      tr.appendChild(td(g.meaning, 'wrap'));
      tr.appendChild(td(g.consequence, 'wrap'));
      tr.appendChild(td(fmt(g.cells), 'num'));
      var bar = document.createElement('div'); bar.className = 'bar'; bar.style.width = Math.max(8, 100 * g.cells / max) + '%';
      [['by_8879', 0], ['on_dev', 1], ['both', 2]].forEach(function (p) {
        var s = document.createElement('span'); s.style.width = (100 * g[p[0]] / g.cells) + '%'; s.style.background = originColor(p[1]); bar.appendChild(s);
      });
      var labels = origins();
      var bc = td(bar); bc.title = labels['8879'] + ': ' + g.by_8879 + ', ' + labels.dev + ': ' + g.on_dev + ', ' + labels.both + ': ' + g.both; tr.appendChild(bc);
      tr.appendChild(td(fmt(g.combos), 'num'));
      tr.appendChild(td(g.worst_effect));
      tr.appendChild(td(g.guard));
      tr.appendChild(td(restoreLinks(g.group)));
      tr.appendChild(td(fmt(g.clients), 'num'));
      tr.appendChild(td(g.basis));
      el.appendChild(tr);
    });
  });

  // Heatmap
  dash.draw('heat', function (el) {
    var h = rows('heat'), gs = rows('groups'); el.replaceChildren(); if (!h || !gs) return;
    var order = gs.map(function (g) { return g.group; });
    var name = {}; gs.forEach(function (g) { name[g.group] = g.name; });
    var cols = []; COL.forEach(function (c) { PATHS.forEach(function (p) { cols.push(c + '|' + p); }); });
    var W = Math.max(el.clientWidth || 800, 832), top = 46;
    var svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', '0 0 ' + W + ' 10');
    var probe = svg.append('text').attr('font-size', 12);
    var lw = d3.max(order, function (g) { probe.text(name[g]); return probe.node().getComputedTextLength(); }) + 14;
    probe.remove();
    var x = d3.scaleBand(cols, [lw, W - 4]).paddingInner(0.12);
    var rowH = Math.min(26, Math.max(18, x.bandwidth()));
    var y = d3.scaleBand(order, [top, top + order.length * rowH]).paddingInner(0.12);
    var H = top + order.length * rowH + 8;
    svg.attr('viewBox', '0 0 ' + W + ' ' + H);
    var max = d3.max(h, function (d) { return d.cells; });
    var cs = getComputedStyle(el);
    var lo = cs.getPropertyValue('--cds-chart-grid').trim() || '#ddd';
    var color = d3.scaleLog([1, max], [0.25, 1]).clamp(true);
    var tip = tooltip(el);
    COL.forEach(function (c, i) {
      var x0 = x(c + '|v1'), x1 = x(c + '|ws') + x.bandwidth();
      svg.append('text').attr('x', (x0 + x1) / 2).attr('y', 12).attr('text-anchor', 'middle').attr('font-size', 12).style('fill', 'var(--color-fg)').text(c);
      PATHS.forEach(function (p) {
        svg.append('text').attr('x', x(c + '|' + p) + x.bandwidth() / 2).attr('y', 32).attr('text-anchor', 'middle').attr('font-size', 10).text(p === 'inproc' ? 'in' : p);
      });
      if (i > 0) svg.append('line').attr('x1', x0 - 3).attr('x2', x0 - 3).attr('y1', 4).attr('y2', H - 4).attr('stroke', 'var(--cds-chart-axis)').attr('stroke-opacity', 0.5);
    });
    order.forEach(function (g) {
      svg.append('text').attr('x', 0).attr('y', y(g) + y.bandwidth() / 2).attr('dy', '0.35em').attr('font-size', 12)
        .style('fill', g === 'n' ? 'var(--color-bad)' : 'var(--color-fg)').text(name[g]);
      cols.forEach(function (k) {
        svg.append('rect').attr('x', x(k)).attr('y', y(g)).attr('width', x.bandwidth()).attr('height', y.bandwidth()).attr('rx', 2).attr('fill', lo).attr('fill-opacity', 0.35);
      });
    });
    var sel = window.cwState.cellHeat;
    svg.append('g').selectAll('rect').data(h).join('rect')
      .attr('x', function (d) { return x(d.collection + '|' + d.path); }).attr('y', function (d) { return y(d.group); })
      .attr('width', x.bandwidth()).attr('height', y.bandwidth()).attr('rx', 2)
      .attr('fill', function (d) { return d.group === 'n' ? 'var(--cds-chart-status-critical)' : dash.colors[0]; })
      .attr('fill-opacity', function (d) { return color(d.cells); })
      .attr('stroke', function (d) { return sel && sel.group === d.group && sel.collection === d.collection && sel.path === d.path ? 'var(--color-fg)' : 'none'; })
      .attr('stroke-width', 2).style('cursor', 'pointer')
      .on('mousemove', function (ev, d) { tip.show(ev, [name[d.group], d.collection + ', re-sent over ' + d.path, fmt(d.cells) + ' cells']); })
      .on('mouseleave', tip.hide)
      .on('click', function (ev, d) {
        window.cwState.cellHeat = { group: d.group, collection: d.collection, path: d.path };
        window.cwState.cellGroup = d.group;
        document.querySelectorAll('#cell-g').forEach(function (s) { s.value = d.group; });
        dash.draw('heat'); dash.draw('cells-body'); dash.draw('cell-count');
        document.querySelectorAll('#cells').forEach(function (s) { s.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
      });
  });

  // Triage table
  function triageRows() {
    var r = rows('triage'); if (!r) return null;
    var q = ''; document.querySelectorAll('#tri-q').forEach(function (i) { q = i.value.trim().toLowerCase(); });
    var v = ''; document.querySelectorAll('#tri-v').forEach(function (i) { v = i.value; });
    var out = r.filter(function (d) {
      if (v && d.verdict !== v) return false;
      if (!q) return true;
      return (d.clients + ' ' + d.collection + ' ' + d.name + ' ' + d.path + ' ' + d.effect).toLowerCase().indexOf(q) !== -1;
    });
    var k = window.cwState.tSort, dir = window.cwState.tDir;
    out.sort(function (a, b) { var x = a[k], y = b[k]; return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y))) * dir; });
    return out;
  }
  dash.draw('triage-body', function (el) {
    var r = triageRows(); el.replaceChildren(); if (!r) return;
    var all = rows('triage'), max = d3.max(all, function (d) { return d.score; });
    r.forEach(function (d) {
      var tr = document.createElement('tr'); tr.dataset.key = d.key;
      var wrap = document.createElement('div'); wrap.style.display = 'flex'; wrap.style.gap = '0.4rem'; wrap.style.alignItems = 'center';
      var bar = document.createElement('div'); bar.className = 'bar'; bar.style.width = '4rem';
      var s = document.createElement('span'); s.style.width = (100 * d.score / max) + '%';
      s.style.background = d.verdict === 'Defect' ? 'var(--cds-chart-status-critical)' : dash.colors[0]; bar.appendChild(s);
      var n = document.createElement('span'); n.textContent = d3.format('.3~f')(d.score);
      wrap.appendChild(n); wrap.appendChild(bar);
      tr.appendChild(td(wrap));
      tr.appendChild(td(chip(d.verdict, VCLASS[d.verdict])));
      tr.appendChild(td(d.name));
      tr.appendChild(td(d.collection));
      tr.appendChild(td(d.path));
      tr.appendChild(td(fmt(d.cells), 'num'));
      tr.appendChild(td(d.effect));
      tr.appendChild(td(chip(d.evidence === 'no' ? 'no client' : d.evidence, d.evidence === 'measured' ? 'measured' : (d.evidence === 'read' ? 'read' : 'noclient'))));
      tr.appendChild(td(d.clients, 'wrap'));
      el.appendChild(tr);
    });
  });
  dash.draw('triage-count', function (el) {
    var r = triageRows(), all = rows('triage');
    el.textContent = r ? (fmt(r.length) + ' of ' + fmt(all.length) + ' rows') : '—';
  });
  document.querySelectorAll('#tri-q, #tri-v').forEach(function (i) {
    i.addEventListener('input', function () { dash.draw('triage-body'); dash.draw('triage-count'); });
  });
  document.querySelectorAll('#triage th button[data-sort]').forEach(function (b) {
    b.addEventListener('click', function () {
      var k = b.getAttribute('data-sort');
      if (window.cwState.tSort === k) window.cwState.tDir *= -1; else { window.cwState.tSort = k; window.cwState.tDir = (k === 'score' || k === 'cells') ? -1 : 1; }
      document.querySelectorAll('#triage th').forEach(function (th) { th.removeAttribute('aria-sort'); });
      b.parentElement.setAttribute('aria-sort', window.cwState.tDir < 0 ? 'descending' : 'ascending');
      dash.draw('triage-body');
    });
  });

  // Client x change dot matrix
  dash.draw('clientmap', function (el) {
    var c = rows('clients'), gs = rows('groups'); el.replaceChildren(); if (!c || !gs) return;
    var name = {}; gs.forEach(function (g) { name[g.group] = g.name; });
    var groupsUsed = gs.map(function (g) { return g.group; }).filter(function (g) { return c.some(function (d) { return d.group === g; }); });
    var agg = d3.rollups(c, function (v) {
      return { n: v.length, tier: v.some(function (d) { return d.tier === 'measured'; }) ? 'measured' : 'read', where: Array.from(new Set(v.map(function (d) { return d.collection + ' ' + d.path; }))).join(', ') };
    }, function (d) { return d.client; }, function (d) { return d.group; });
    var clients = agg.map(function (a) { return a[0]; }).sort(function (a, b) {
      return d3.sum(agg.find(function (x) { return x[0] === b; })[1], function (d) { return d[1].n; }) - d3.sum(agg.find(function (x) { return x[0] === a; })[1], function (d) { return d[1].n; });
    });
    var W = Math.max(el.clientWidth || 700, 704), top = 150;
    var svg = d3.select(el).append('svg').attr('width', '100%').attr('viewBox', '0 0 ' + W + ' 10');
    var probe = svg.append('text').attr('font-size', 12);
    var lw = d3.max(clients, function (s) { probe.text(s); return probe.node().getComputedTextLength(); }) + 14;
    probe.remove();
    var x = d3.scaleBand(groupsUsed, [lw, W - 10]).padding(0.1);
    var rowH = 26, y = d3.scaleBand(clients, [top, top + clients.length * rowH]).padding(0.1);
    var H = top + clients.length * rowH + 6;
    svg.attr('viewBox', '0 0 ' + W + ' ' + H);
    var r = d3.scaleSqrt([1, d3.max(agg, function (a) { return d3.max(a[1], function (d) { return d[1].n; }); })], [3, Math.min(10, rowH / 2 - 2)]);
    var tip = tooltip(el);
    groupsUsed.forEach(function (g) {
      var cx = x(g) + x.bandwidth() / 2;
      svg.append('text').attr('transform', 'translate(' + cx + ',' + (top - 8) + ') rotate(-55)').attr('font-size', 11)
        .style('fill', g === 'n' ? 'var(--color-bad)' : 'var(--color-fg-muted)').text(name[g]);
      svg.append('line').attr('x1', cx).attr('x2', cx).attr('y1', top).attr('y2', H - 4).attr('stroke', 'var(--cds-chart-grid)');
    });
    clients.forEach(function (cl) {
      var cy = y(cl) + y.bandwidth() / 2;
      svg.append('text').attr('x', 0).attr('y', cy).attr('dy', '0.35em').attr('font-size', 12).style('fill', 'var(--color-fg)').text(cl);
      svg.append('line').attr('x1', lw).attr('x2', W - 10).attr('y1', cy).attr('y2', cy).attr('stroke', 'var(--cds-chart-grid)');
      agg.find(function (a) { return a[0] === cl; })[1].forEach(function (pair) {
        var g = pair[0], v = pair[1];
        svg.append('circle').attr('cx', x(g) + x.bandwidth() / 2).attr('cy', cy).attr('r', r(v.n))
          .attr('fill', v.tier === 'measured' ? 'var(--color-ok)' : 'var(--color-warn)').attr('fill-opacity', 0.85)
          .on('mousemove', function (ev) { tip.show(ev, [cl, name[g] + ' (' + v.tier + ')', v.where]); }).on('mouseleave', tip.hide);
      });
    });
  });

  // Cell explorer
  dash.draw('cell-groups', function (sel) {
    var gs = rows('groups');
    sel.replaceChildren(new Option('All changes', ''));
    (gs || []).forEach(function (g) { sel.appendChild(new Option(g.name + ' (' + fmt(g.cells) + ')', g.group)); });
    sel.value = window.cwState.cellGroup || '';
    sel.onchange = function () { window.cwState.cellGroup = sel.value; window.cwState.cellHeat = null; dash.draw('cells-body'); dash.draw('cell-count'); dash.draw('heat'); };
  });
  var LIMIT = 400;
  function cellRows() {
    var r = rows('cells'); if (!r) return null;
    var st = window.cwState, q = '';
    document.querySelectorAll('#cell-q').forEach(function (i) { q = i.value.trim().toLowerCase(); });
    return r.filter(function (d) {
      if (st.cellGroup && d.group !== st.cellGroup) return false;
      if (st.cellHeat && (d.collection !== st.cellHeat.collection || d.resend !== st.cellHeat.path)) return false;
      return !q || (d.cell + ' ' + d.cause).toLowerCase().indexOf(q) !== -1;
    });
  }
  dash.draw('cells-body', function (el) {
    var r = cellRows(); el.replaceChildren(); if (!r) return;
    r.slice(0, LIMIT).forEach(function (d) {
      var tr = document.createElement('tr'); tr.dataset.key = d.cell;
      tr.appendChild(td(d.cell, 'mono'));
      tr.appendChild(td(d.origin));
      tr.appendChild(td(d.effect));
      tr.appendChild(td(d.store_before, 'mono'));
      tr.appendChild(td(d.store_after, 'mono'));
      tr.appendChild(td(d.reply_before, 'mono'));
      tr.appendChild(td(d.reply_after, 'mono'));
      tr.appendChild(td(d.cause, 'wrap'));
      el.appendChild(tr);
    });
  });
  dash.draw('cell-count', function (el) {
    var r = cellRows(); if (!r) { el.textContent = '—'; return; }
    var h = window.cwState.cellHeat;
    el.textContent = fmt(r.length) + ' cells' + (h ? ' on ' + h.collection + ', re-sent over ' + h.path : '') + (r.length > LIMIT ? '; showing the first ' + LIMIT + ', narrow with the filters' : '');
  });
  document.querySelectorAll('#cell-q').forEach(function (i) { i.addEventListener('input', function () { dash.draw('cells-body'); dash.draw('cell-count'); }); });
  document.querySelectorAll('#cell-clear').forEach(function (b) {
    b.addEventListener('click', function () {
      window.cwState.cellGroup = ''; window.cwState.cellHeat = null;
      document.querySelectorAll('#cell-q').forEach(function (i) { i.value = ''; });
      document.querySelectorAll('#cell-g').forEach(function (s) { s.value = ''; });
      dash.draw('cells-body'); dash.draw('cell-count'); dash.draw('heat');
    });
  });
})();
