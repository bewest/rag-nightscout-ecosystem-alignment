#!/usr/bin/env python3
"""Render the source-attributed tenancy topology plates (SVG and optional PNG).

Uses only Python's standard library for SVG. --png additionally invokes the
installed ImageMagick `convert` renderer; it installs nothing or starts services.
"""
from __future__ import annotations
import argparse
import html
from pathlib import Path
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/30-design/tenancy/diagrams'
W = 1600
INK = '#203248'
MUTED = '#52647a'
TEAL = '#147d83'
BLUE = '#365aa2'
AMBER = '#956116'


class Plate:
    def __init__(self, title, subtitle, badge, proposed=False):
        self.parts = []
        self.arrows = []
        self.proposed = proposed
        self.rect(0, 0, W, 2400, '#ffffff', 'none', radius=0)
        self.text(48, 56, title, 34, weight='700')
        self.text(48, 93, subtitle, 20, MUTED)
        self.rect(48, 118, 1504, 55, '#fff4dd' if proposed else '#e7f4ef', 'none')
        self.text(68, 153, badge, 21, AMBER if proposed else '#24654a', '700')

    def text(self, x, y, value, size=20, color=INK, weight='400', anchor='start'):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{html.escape(value)}</text>')

    def rect(self, x, y, w, h, fill='#fff', stroke='#c8d3e0', radius=12, dash=False):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{chr(32)+"stroke-dasharray=\"7 5\"" if dash else ""}/>')

    def lines(self, x, y, values, size=19, color=MUTED, step=27, anchor='start'):
        for i, value in enumerate(values):
            self.text(x, y + i * step, value, size, color, anchor=anchor)

    def arrow(self, points, color=BLUE):
        coords = ' '.join(f'{x},{y}' for x, y in points)
        self.arrows.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        x, y = points[-1]
        self.arrows.append(f'<polygon points="{x-5},{y-9} {x+5},{y-9} {x},{y}" fill="{color}"/>')

    def zone(self, y, h, title, subtitle, fill):
        self.rect(32, y, 1536, h, fill, '#d8e0e9', radius=14)
        self.text(52, y+30, title, 18, MUTED, '700')
        self.text(1548, y+30, subtitle, 17, MUTED, anchor='end')

    def card(self, x, y, w, title, lines, terminal=None, h=110):
        self.rect(x, y, w, h)
        self.text(x+18, y+(27 if h<85 else 32), title, 23, INK, '700')
        self.lines(x+18, y+(50 if h<85 else 60), lines, 18, step=25)
        if terminal:
            self.text(x+18, y+h-15, terminal, 16, TEAL, '600')

    def table(self, y, rows):
        self.text(48, y, 'Communication planes — exact bindings, separate from placement', 25, INK, '700')
        y += 22
        cols = [48, 165, 608, 1552]
        self.rect(48, y, 1504, 43, '#e8edf4', 'none', radius=0)
        for x, title in zip(cols, ['PLANE', 'FROM → TO', 'BOUNDARY / TRANSPORT']):
            self.text(x+12, y+28, title, 16, MUTED, '700')
        y += 43
        for i, (plane, route, body) in enumerate(rows):
            route_lines = textwrap.wrap(route, width=36)
            body_lines = textwrap.wrap(body, width=82)
            height = max(len(route_lines), len(body_lines))*25+24
            self.rect(48, y, 1504, height, '#f5f8fb' if i%2==0 else '#ffffff', 'none', radius=0)
            self.text(60, y+29, plane, 18, TEAL, '700')
            self.lines(177, y+29, route_lines, 18, INK, 25)
            self.lines(620, y+29, body_lines, 18, MUTED, 25)
            y += height
        return y

    def finish(self, y, filename):
        height = y+35
        defs = '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="'+BLUE+'"/></marker></defs>'
        label = html.escape(filename.replace('-', ' '))
        content = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" role="img" aria-labelledby="title desc"><title id="title">{label}</title><desc id="desc">Top-to-bottom trust zones, logical endpoints and role instances. Communication planes are listed explicitly to avoid ambiguous crossing connections. Physical placement is stated separately.</desc>{defs}<g font-family="DejaVu Sans, sans-serif">'+''.join(self.parts + self.arrows)+'</g></svg>\n'
        path = OUT / (filename+'.svg')
        path.write_text(content)
        return path


def accepted():
    p = Plate('Accepted one-host reference', 'Source-attributed structure • synthetic deployment • no production admission', 'ACCEPTED BOUNDED REFERENCE  |  ed2 cold Compose/UI/restore; c23 native restart proof')
    p.zone(198, 134, '1  CLIENT / LAB INGRESS', 'Reachability is not tenant authority', '#f1f5fb')
    p.card(300, 246, 1000, 'Synthetic clients, browsers and tenant aliases', ['Lab DNS / hosts → host-published HTTP address; no accepted external L4 load balancer'], h=70)
    p.arrow([(800,316),(800,350)])
    p.zone(350, 167, '2  EDGE TRUST BOUNDARY', 'Accepted public-facing protocol: HTTP', '#eef6f6')
    p.card(64, 392, 1472, 'nginx — logical routing', ['Preserve configured Host; strip selector headers; public owner/operator paths refused'], h=94)
    p.zone(535, 105, '3  LOGICAL PUBLIC ENDPOINTS', 'Endpoints are not extra processes', '#f3f5fa')
    for x,w,title,lines in [(64,456,'UI / assets',['Shipping UI']), (572,456,'DATA / API',['Existing versioned routes']), (1080,456,'DATA / realtime',['Main and alarm sockets'])]:
        p.card(x,577,w,title,lines,h=60)
    for x in [292,800,1308]:
        p.arrow([(x,486),(x,535)])
    p.zone(659, 330, '4  PRIVATE APPLICATION RUNTIME', 'Separate role processes; fixed participant roster', '#f8f9fb')
    for x,title,lines,terminal in [(64,'UI process',['Templates and assets','No DB credentials'],'DATA: public edge only'),(572,'API process',['Request frames / writes','Current tenant authority'],'PG: role grant  ·  Vault: scoped'),(1080,'Realtime process',['Owns connections / frames','Forwards mutations to API'],'PG: reader grant  ·  U1 / U2')]:
        p.card(x,706,456,title,lines,terminal,h=120)
    for x in [292,800,1308]:
        p.arrow([(x,637),(x,659)])
    for x,title,lines,term in [(64,'Evaluator process',['Clinical projection / intents','One active reference instance'],'PG: declared grant  ·  U2'),(572,'Tenant-admin process',['OWNER control, private','Separate audience / listener'],'PG: management grant  ·  C'),(1080,'Maintenance controller',['Private operator invocation','Addresses each participant'],'PG: maintenance grant  ·  C')]:
        p.card(x,846,456,title,lines,term,h=120)
    p.rect(48,1006,1504,55,'#edf1f6','none')
    p.text(68,1040,'PHYSICAL PLACEMENT: one host / Compose backend network; private shared Unix-socket directory.',19,INK,'600')
    p.zone(1079,157,'5  BACKING RESOURCES', 'Authority and durable state; per-role grants, no implied all-to-all access', '#f0f7f3')
    for x,title,lines in [(64,'PostgreSQL',['Tenant data, authority, operations','Direct connections / forced RLS']), (572,'Vault Transit — TLS',['Scoped protected keys / secrets','Generated lab credentials']), (1080,'Recovery artifacts',['Explicit operator-owned snapshots','Separate from disposable runtime'])]:
        p.card(x,1121,456,title,lines,h=100)
    y=p.table(1280,[
        ('DATA','Edge → UI / API / realtime','HTTP public origin inside the synthetic reference. Owner and operator routes are refused at this edge.'),
        ('U1','Realtime → API','HTTP POST/JSON over private Unix socket; authorization and mutation forwarding preserve current tenant/client authority.'),
        ('U2','Evaluator → realtime','Private Unix socket alarm/notification handoff. Raw socket frames and evaluator-derived values remain different products.'),
        ('C','Controller → API, realtime, evaluator, tenant-admin','Private Unix control sockets: fixed per-instance roster, pinned incarnation, drain and invalidation acknowledgement. Never a load-balanced substitute.'),
        ('STORE','Role → PostgreSQL / scoped Vault','Each role uses its own effective grant. API uses the scoped secret provider. UI/nginx have no DB credentials. Bootstrap is explicit operator work.'),
        ('OWNER','Private owner client → tenant-admin','Separate authenticated owner listener/audience. No public owner route in the accepted Compose edge; maintenance is never a public endpoint.'),
    ])
    p.text(48,y+36,'Source scope: ed2ced00 cold image/UI/restore/client evidence; c23cf1f3 native separate-role restart evidence.',18,MUTED)
    p.text(48,y+64,'No OIDC capability, external ingress TLS, multi-host transport, HA or capacity acceptance is implied.',18,AMBER,'600')
    p.text(48,y+92,'Evidence: reports/tenancy/operation-window-acceptance-2026-11-07/README.md',17,MUTED)
    return p.finish(y+105,'accepted-one-host-topology')


def proposed():
    p=Plate('Proposed fixed-roster network target','Logical service endpoints • explicit instances • topology and transport require acceptance','PROPOSED — NOT IMPLEMENTED / NOT ACCEPTED  |  Fixed API scale-out; singleton evaluator and realtime',True)
    p.zone(198,115,'1  PUBLIC / DMZ', 'DNS supplies reachability, not permission', '#f1f5fb')
    p.card(300,241,1000,'Clients / browsers → public DNS name',['Permanent or temporary name binds to current tenant/access policy'],h=64)
    p.arrow([(800,305),(800,332)])
    p.zone(332,115,'2  PUBLIC REACHABILITY', 'L4 transport routing, not application authority', '#eef3fb')
    p.card(300,369,1000,'Public address / L4 load balancer',['Forwards to the declared trusted edge; peer/source-address behavior must be measured'],h=70)
    p.arrow([(800,439),(800,466)])
    p.zone(466,126,'3  TRUSTED HTTP EDGE', 'TLS + Host / client identity / access-policy boundary', '#eef6f6')
    p.card(64,503,1472,'nginx — TLS termination and logical routing',['DATA paths and socket upgrades; OWNER only through separately authenticated route/listener'],h=76)
    p.zone(610,100,'4  LOGICAL SERVICE ENDPOINTS', 'Not an all-role load-balancing layer', '#f3f5fa')
    for x,w,title,lines in [(64,330,'UI endpoint',['Pages / assets']),(436,728,'API service endpoint',['Selects one admitted API1 / API2 instance']),(1206,330,'Realtime endpoint',['One connection owner'])]:
        p.card(x,650,w,title,lines,h=58)
    for x in [229,800,1371]:p.arrow([(x,579),(x,610)])
    p.zone(730,327,'5  PRIVATE APPLICATION RUNTIME', 'Fixed roster; no autoscaling / dynamic membership claim', '#f8f9fb')
    for x,title,lines,term in [(64,'UI process',['Templates / assets'],'No DB grant'),(436,'API1',['Stateless request serving','Reconstructible local state'],'PG role grant  ·  N1 / C1'),(808,'API2',['Stateless request serving','Reconstructible local state'],'PG role grant  ·  N1 / C2'),(1180,'Realtime',['Owns connected sockets','Single target instance'],'PG reader grant  ·  N2 / C3')]:
        p.card(x,780,356,title,lines,term,h=120)
    p.arrow([(229,708),(229,730)])
    p.arrow([(614,708),(614,730)])
    p.arrow([(986,708),(986,730)])
    p.arrow([(1358,708),(1358,730)])
    for x,title,lines,term in [(64,'Evaluator — one producer',['Singleton; no replication','Stable partitions are future work'],'PG declared grant  ·  N2 / C4'),(572,'Tenant-admin',['Private OWNER control','Separate auth and listener'],'PG management grant  ·  C5'),(1080,'Private maintenance controller',['Platform/config roster input','C1…C5 per-instance fanout'],'PG maintenance grant  ·  C')]:
        p.card(x,920,456,title,lines,term,h=120)
    p.rect(48,1073,1504,62,'#fff4dd','none')
    p.text(68,1100,'PHYSICAL PLACEMENT: proposed generic hosts / node pools carry this same fixed roster; zones above are trust zones.',18,INK,'600')
    p.text(68,1125,'Host count does not select replica ownership. L4/API load balancing never replaces per-instance maintenance endpoints.',18,MUTED)
    p.zone(1153,158,'6  BACKING RESOURCES', 'Durability, recovery and effective grants remain explicit', '#f0f7f3')
    for x,title,lines in [(64,'PostgreSQL',['Tenant / operation authority','Aggregate API pools need limits']), (572,'Vault Transit — TLS',['Scoped keys / service login','Renewal and recovery admission']), (1080,'Durable recovery artifacts',['Declared store and ownership','Verify restores and retained keys'])]:
        p.card(x,1195,456,title,lines,h=100)
    p.zone(1328,101,'EXTERNAL HUMAN IDENTITY — SEPARATE CAPABILITY', 'Source capability; not accepted in ed2', '#f8f0fc')
    p.text(68,1387,'OIDC IdP ↔ optional shared human-session integration: separate current-authority adapter; no implicit DATA/root grant.',19,MUTED)
    y=p.table(1472,[
        ('DATA','Edge → UI / API service / realtime','TLS public ingress; tenant selection, current access policy and client authority still apply. Public operator ingress is forbidden.'),
        ('N1','Realtime → API service → API1 or API2','Proposed configurable Unix or HTTP(S) client/listener binding. Network trust authenticates the internal caller; tenant/client authorization stays unchanged.'),
        ('N2','Evaluator singleton → realtime singleton','Proposed qualified network alarm/notification handoff. Replicating realtime would separately require fanout/delivery ownership; not included here.'),
        ('C1…C5','Controller → each exact role instance','Address API1, API2, realtime, evaluator and tenant-admin individually with authenticated identity and pinned incarnation. Status/drain/invalidate cannot use API load balancing.'),
        ('STORE','Each role → declared backing capabilities','Effective per-role PostgreSQL grants; scoped API/secret-provider Vault access. No blanket all-role database, Vault or artifact-store authority.'),
        ('OWNER','Owner client → authenticated private control','Separately authenticated listener or admitted edge route. Optional OIDC requires its own joined provider/session acceptance; operator control remains private.'),
    ])
    p.text(48,y+36,'Network adapter is proposed. HTTP requires an admitted private trust profile; HTTPS still requires caller authorization.',18,AMBER,'600')
    p.text(48,y+64,'Acceptance: concurrent APIs, current authority, all-instance drains/invalidation, replacement, partition, ambiguity and pool/load bounds.',18,MUTED)
    p.text(48,y+92,'No custom membership service/scheduler, dynamic roster, replicated evaluator/realtime or production/HA claim.',18,AMBER,'600')
    p.text(48,y+120,'Design source: docs/30-design/tenancy/deployment-bindings-and-public-names.md (2026-11-08).',17,MUTED)
    return p.finish(y+133,'proposed-fixed-roster-network-topology')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--png',action='store_true',help='Also emit PNG previews using installed ImageMagick convert')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    for path in [accepted(),proposed()]:
        print(path.relative_to(ROOT))
        if args.png:
            png=path.with_suffix('.png')
            subprocess.run(['convert','-background','white',str(path),str(png)],check=True)
            print(png.relative_to(ROOT))


if __name__ == '__main__':
    main()
