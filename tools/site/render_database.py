#!/usr/bin/env python3
"""Render the living multitenant database review from the canonical SQL guide.

Tables, captions and Mermaid bodies come from the guide. Mermaid is rendered to
static SVG with the site's integrity-checked pinned runtime, so reviewing the
page needs neither a CDN request nor browser-side diagram execution.

Run with tools/site/.venv/bin/python tools/site/render_database.py, then set the
page's source_commit in site/pages/pages.yaml to the printed source revision.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown
import mermaid_check

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'docs/30-design/tenancy/sql-and-migration-architecture.md'
OUTPUT = ROOT / 'site/pages/multitenant-database-design.html'
SOURCE_URL = '../../docs/30-design/tenancy/sql-and-migration-architecture.html'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def table(text, header):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('| ' + header + ' |'))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith('|'):
            break
        rows.append([part.strip() for part in line.strip('|').split('|')])
    if not rows or any(len(row) != 3 for row in rows):
        raise ValueError(f'Expected three-column source table: {header}')
    return rows


def inline(text):
    return markdown.markdown(text, extensions=['tables']).removeprefix('<p>').removesuffix('</p>')


def diagrams(text):
    items = []
    heading, caption = '', ''
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('##'):
            heading = line.lstrip('# ')
        if line.startswith('**Read-derived'):
            para = [line]
            j = i + 1
            while j < len(lines) and lines[j].strip():
                para.append(lines[j])
                j += 1
            caption = ' '.join(para)
        if line == '```mermaid':
            body = []
            i += 1
            while i < len(lines) and lines[i] != '```':
                body.append(lines[i])
                i += 1
            items.append({'heading': heading, 'caption': caption, 'code': '\n'.join(body)})
        i += 1
    if not items:
        raise ValueError('No source diagrams found')
    return items


def render_svgs(items):
    runtime = mermaid_check.runtime(mermaid_check.pinned_version())
    with tempfile.TemporaryDirectory(prefix='database-diagrams-') as tmp:
        folder = Path(tmp)
        shutil.copy(runtime, folder / 'mermaid.min.js')
        payload = json.dumps([item['code'] for item in items]).replace('</', '<\\/')
        page = '''<!doctype html><html><head><meta charset="utf-8"></head><body>
<script src="mermaid.min.js"></script><pre id="result"></pre><script>
mermaid.initialize({startOnLoad:false, securityLevel:'strict', deterministicIds:true,
 deterministicIDSeed:'multitenant-database', theme:'neutral',
 flowchart:{htmlLabels:false, curve:'linear'}, themeVariables:{fontSize:'16px'}});
(async()=>{try{const out=[];const codes=PAYLOAD;
 for(let i=0;i<codes.length;i++){const r=await mermaid.render('dbDiagram'+i,codes[i]);out.push(r.svg)}
 document.getElementById('result').textContent=JSON.stringify({svgs:out});
}catch(e){document.getElementById('result').textContent=JSON.stringify({error:String(e)})}})();
</script></body></html>'''.replace('PAYLOAD', payload)
        (folder / 'render.html').write_text(page)
        proc = subprocess.run([mermaid_check.chrome(), '--headless=new', '--disable-gpu',
            '--no-first-run', f'--user-data-dir={folder / "profile"}',
            '--allow-file-access-from-files', '--virtual-time-budget=60000',
            '--dump-dom', (folder / 'render.html').as_uri()], capture_output=True, text=True, timeout=180)
        result = re.search(r'<pre id="result">(.*?)</pre>', proc.stdout, re.S)
        if not result or not result[1]:
            raise RuntimeError('Diagram renderer did not finish: ' + proc.stderr[-400:])
        data = json.loads(html.unescape(result[1]))
        if 'error' in data:
            raise RuntimeError(data['error'])
        if len(data['svgs']) != len(items):
            raise RuntimeError('Incomplete SVG rendering')
        return data['svgs']


CSS = '''
:root{color-scheme:light dark;--bg:#f7f8fa;--paper:#fff;--ink:#1e293b;--muted:#536176;--line:#cbd5e1;--accent:#175d8d;--tint:#e9f2f8}
@media(prefers-color-scheme:dark){:root{--bg:#141b25;--paper:#1f2937;--ink:#edf2f7;--muted:#bcc7d5;--line:#526174;--accent:#91c9f0;--tint:#22394c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:32px 24px 64px}a{color:var(--accent);text-underline-offset:3px}h1,h2,h3,p{margin:0}h1{font-size:clamp(1.8rem,4vw,2.8rem);line-height:1.15;max-width:25ch}h2{font-size:1.6rem;line-height:1.3}h3{font-size:1.05rem}header{display:grid;gap:16px;margin-bottom:28px}.eyebrow{color:var(--accent);font-size:.85rem;letter-spacing:.06em;text-transform:uppercase}.provenance{color:var(--muted);font-size:.9rem}.contract{border-left:4px solid var(--accent);padding:12px 18px;background:var(--tint)}nav{display:flex;gap:12px 24px;flex-wrap:wrap;border-block:1px solid var(--line);padding:14px 0}section{margin-top:40px;scroll-margin-top:20px}.intro{color:var(--muted);margin:8px 0 20px}.family-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.family,.owner{background:var(--paper);border:1px solid var(--line);padding:18px;border-radius:6px;min-width:0}.family h3{color:var(--accent);margin-bottom:10px}.family p{margin:8px 0}.families-code{font-size:.92rem}code{overflow-wrap:anywhere}.owners{display:grid;gap:12px}.owner{display:grid;grid-template-columns:minmax(140px,.7fr) minmax(0,1fr) minmax(0,1.2fr);gap:20px;align-items:start}.owner h3{color:var(--accent)}.owner .label{display:block;color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}.owner .write{border-left:3px solid var(--accent);padding-left:14px}.diagram-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.diagram{min-width:0;margin:0;background:var(--paper);border:1px solid var(--line);padding:20px;border-radius:6px}.diagram.wide{grid-column:1/-1}.diagram h3{margin-bottom:8px}.diagram figcaption{font-size:.9rem;color:var(--muted);margin-top:12px}.svg-scroll{overflow-x:auto;margin:16px 0;background:#fff;color:#222;border-radius:4px;padding:12px}.svg-scroll svg{display:block;max-width:none!important;height:auto;min-width:100%}details{margin-top:10px;font-size:.9rem}summary{cursor:pointer;color:var(--accent)}footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted)}:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
@media(max-width:760px){main{padding:24px 16px 40px}.family-grid,.diagram-grid{grid-template-columns:1fr}.owner{grid-template-columns:1fr;gap:12px}.diagram{padding:14px}.diagram.wide{grid-column:auto}}
@media print{body{background:#fff;color:#111}nav{display:none}main{max-width:none}.svg-scroll{overflow:visible}.svg-scroll svg{max-width:100%!important;min-width:0}.diagram{break-inside:avoid}.family-grid{grid-template-columns:1fr 1fr}}
'''


def main():
    if git('status', '--porcelain', '--', SOURCE):
        raise SystemExit('Commit the canonical SQL source before rendering its living review page')
    text = (ROOT / SOURCE).read_text()
    sha = git('log', '-1', '--format=%H', '--', SOURCE)
    items = diagrams(text)
    svgs = render_svgs(items)
    # Select the storage-ownership table explicitly, rather than the later scale-out table.
    ownership_text = text.split('### Component storage ownership', 1)[1].split('### Lifecycle control boundary', 1)[0]
    owners = ''.join(f'<div class="owner"><h3>{inline(r[0])}</h3><div><span class="label">Admitted reads</span>{inline(r[1])}</div><div class="write"><span class="label">Owned persistence / controlled writes</span>{inline(r[2])}</div></div>' for r in table(ownership_text, 'Component'))
    families = ''.join(f'<article class="family"><h3>{inline(r[0])}</h3><p class="families-code">{inline(r[1])}</p><details><summary>Relationship and restore treatment</summary><p>{inline(r[2])}</p></details></article>' for r in table(text, 'Family'))
    gallery = []
    for i, (item, svg) in enumerate(zip(items, svgs)):
        # Keep intrinsic geometry: narrow screens scroll instead of shrinking labels.
        view = re.search(r'viewBox="([^"]+)"', svg)
        width = float(view[1].split()[2]) if view else 900
        svg = re.sub(r'<svg\b', f'<svg aria-label="{html.escape(item["heading"], quote=True)}" style="width:{width:.1f}px"', svg, count=1)
        # Duplicate Mermaid's generic style attribute would be invalid HTML.
        svg = re.sub(r'(<svg[^>]*?) style="max-width:[^"]*"', r'\1', svg, count=1)
        wide = ' wide' if width > 520 or item['code'].startswith('sequenceDiagram') else ''
        gallery.append(f'<figure class="diagram{wide}" id="diagram-{i}"><h3>{html.escape(item["heading"])}</h3><div class="svg-scroll" tabindex="0" role="region" aria-label="{html.escape(item["heading"], quote=True)} diagram">{svg}</div><figcaption>{inline(item["caption"])}</figcaption></figure>')
    out = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex, nofollow"><title>Multitenant database and component ownership</title><style>{CSS}</style></head><body><main>
<header><div class="eyebrow">Nightscout architecture · visual review</div><h1>Multitenant database and component ownership</h1><p class="provenance">Living contributor-facing view · read-derived design · rendered from the <a href="{SOURCE_URL}">SQL architecture guide</a> at <a href="https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/{sha}/{SOURCE}">{sha[:9]}</a>. Runtime acceptance retains the source guide's evidence and limits.</p><p class="contract">Exclusive ownership belongs to the Nightscout application collectively. Supported internal components and maintenance tools cooperate; external direct writers are unsupported with undefined behavior. <a href="../../releases/cgm-remote-monitor-16.0.0/decisions.html#exclusive-application-postgres-ownership">Supported contract</a>.</p><nav aria-label="Review sections"><a href="#ownership">Component ownership</a><a href="#database">Database families</a><a href="#diagrams">Commands, relationships and sequences</a><a href="../../index.html">Site home</a></nav></header>
<section id="ownership"><h2>Component ownership</h2><p class="intro">Read across each lane: a component can acquire admitted data while owning a distinct persistence responsibility. Cross-owner commands use application interfaces.</p><div class="owners">{owners}</div></section>
<section id="database"><h2>Database families</h2><p class="intro">Logical groups in selected PostgreSQL namespaces. Tenant tables carry tenant_id; schemas organize domains and components. Expand a group for its source-defined restore treatment.</p><div class="family-grid">{families}</div></section>
<section id="diagrams"><h2>Commands, relationships and sequences</h2><p class="intro">Each view answers one question. Commands, logical bindings and declared foreign keys have separate diagrams; sequences preserve ordering. Wide views scroll at their readable size.</p><div class="diagram-grid">{''.join(gallery)}</div></section>
<footer><a href="{SOURCE_URL}">Full SQL design and evidence</a> · <a href="{SOURCE_URL}#kubernetes-scalability-smell-test">Kubernetes replica assessment</a> · <a href="../../docs/30-design/tenancy/evaluator-realtime-communication.html">Runtime communication</a><p>These figures describe the admitted reference and design direction; they do not establish new production, Kubernetes or capacity acceptance.</p></footer>
</main></body></html>'''
    OUTPUT.write_text(out)
    print(f'Rendered {OUTPUT.relative_to(ROOT)} from {SOURCE} at {sha}; {len(items)} static SVG diagrams')
    print(f'source_commit: {sha}')


if __name__ == '__main__':
    main()
