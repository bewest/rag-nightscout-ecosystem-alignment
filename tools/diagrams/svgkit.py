"""Shared drawing pieces for the figures in tools/diagrams.

Same card, font and text measure as tools/structure-diagrams/render.py, so these figures sit beside
the control-structure drawings: a white card (readable in either colour scheme), Helvetica metrics,
dark ink. Every number written to SVG goes through num(), so the output is byte-stable.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "structure-diagrams"))
from render import FONT, tw  # noqa: E402

OUT = REPO / "docs" / "30-design" / "platform" / "diagrams"

W = 720                       # drawing width; the site shows figures about 688 px wide on a 1440 px desktop, so 12 px text displays near 11.5 px
INK, MUTED, RULE, CARD, FAINT = "#111111", "#555555", "#c8c8c8", "#ffffff", "#f4f4f4"
FS, FS_SMALL, FS_TITLE = 12.5, 12, 14
# two series (the hubs, or written vs derived) from the structure drawings' control/feedback pair;
# validated as an adjacent pair with the dataviz validator (light surface)
BLUE, ORANGE = "#1f5fa8", "#b5541b"
BLUE_T, ORANGE_T = "#dce7f5", "#f6e0d2"
# status steps, from tools/structure-diagrams/access_charts.py; always with a glyph and a word
BAD_T, BAD = "#f7dede", "#d03b3b"
GOOD_T, GOOD = "#e2f3e2", "#0ca30c"


def num(x):
    """A coordinate as text: one decimal, no trailing .0."""
    s = f"{float(x):.1f}"
    return s[:-2] if s.endswith(".0") else s


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def text(x, y, s, size=FS, fill=INK, anchor="start", weight=None, italic=False, halo=False):
    """halo: a background-coloured box under the text, so a line behind it stays readable."""
    h = ""
    if halo:
        wd = tw(s, size)
        bx = x - wd if anchor == "end" else x - wd / 2 if anchor == "middle" else x
        h = rect(bx - 1, y - size * 0.8, wd + 2, size * 1.05, halo if isinstance(halo, str) else FAINT)
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    w = f' font-weight="{weight}"' if weight else ""
    i = ' font-style="italic"' if italic else ""
    return h + f'<text x="{num(x)}" y="{num(y)}" font-size="{num(size)}" fill="{fill}"{a}{w}{i}>{esc(s)}</text>'


def rect(x, y, w, h, fill, stroke=None, rx=0, dash=None, sw=1):
    st = f' stroke="{stroke}" stroke-width="{num(sw)}"' if stroke else ""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    r = f' rx="{num(rx)}"' if rx else ""
    return f'<rect x="{num(x)}" y="{num(y)}" width="{num(max(w, 0))}" height="{num(h)}"{r} fill="{fill}"{st}{d}/>'


def line(x1, y1, x2, y2, stroke=RULE, sw=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}" stroke="{stroke}" '
            f'stroke-width="{num(sw)}"{d}/>')


def arrow_right(x, y, color, size=6):
    return (f'<path d="M{num(x)},{num(y - size / 2)} L{num(x + size)},{num(y)} L{num(x)},{num(y + size / 2)} Z" '
            f'fill="{color}"/>')


def cross(x, y, color, r=4.5, sw=2):
    return (f'<path d="M{num(x - r)},{num(y - r)} L{num(x + r)},{num(y + r)} M{num(x - r)},{num(y + r)} '
            f'L{num(x + r)},{num(y - r)}" stroke="{color}" stroke-width="{num(sw)}" fill="none"/>')


def tick(x, y, color, filled=True, r=4):
    f = color if filled else CARD
    return f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(r)}" fill="{f}" stroke="{color}" stroke-width="1.5"/>'


BOLD = 1.08                   # bold Helvetica runs about this much wider than the regular metrics


def wrap(s, width, size=FS, bold=False):
    out, cur = [], ""
    for word in str(s).split():
        t = (cur + " " + word).strip()
        if cur and tw(t, size) * (BOLD if bold else 1) > width:
            out.append(cur)
            cur = word
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def fit(s, width, size=FS):
    """The string, cut with an ellipsis if wider than width."""
    s = str(s)
    if tw(s, size) <= width:
        return s
    while s and tw(s + "…", size) > width:
        s = s[:-1]
    return s + "…"


def overflow(body, width):
    """Text elements whose measured extent passes the card's right edge or starts left of 0."""
    import re
    bad = []
    for el in body:
        for m in re.finditer(r'<text x="([-\d.]+)" y="[-\d.]+" font-size="([\d.]+)"([^>]*)>([^<]*)</text>', el):
            a = re.search(r'text-anchor="(\w+)"', m.group(3))
            x, size, anchor = float(m.group(1)), float(m.group(2)), a.group(1) if a else "start"
            s = m.group(4).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            wd = tw(s, size) * (BOLD if 'font-weight="bold"' in m.group(3) else 1)
            x0 = x - wd if anchor == "end" else x - wd / 2 if anchor == "middle" else x
            if x0 < 0 or x0 + wd > width - 4:
                bad.append(s)
    return bad


def svg(width, height, title, desc, body):
    bad = overflow(body, width)
    if bad:
        raise SystemExit(f"{title}: text past the card edge: {bad}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{num(width)}" height="{num(height)}" '
            f'viewBox="0 0 {num(width)} {num(height)}" font-family="{FONT}" role="img">\n'
            f'<title>{esc(title)}</title>\n<desc>{esc(desc)}</desc>\n'
            + rect(0, 0, width, height, CARD) + "\n" + "\n".join(body) + "\n</svg>\n")


def iso(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def hhmm(s):
    return iso(s).strftime("%H:%M")


class Lanes:
    """Place labels in a row without overlap: a label that would touch one already placed goes
    to the next sub-row. Returns the sub-row index for each placement."""

    def __init__(self, gap=6):
        self.rows, self.gap = [], gap

    def place(self, x0, x1):
        for i, spans in enumerate(self.rows):
            if all(x1 + self.gap <= a or x0 >= b + self.gap for a, b in spans):
                spans.append((x0, x1))
                return i
        self.rows.append([(x0, x1)])
        return len(self.rows) - 1


class Axis:
    """A linear time axis in minutes, mapped to [x0, x1]."""

    def __init__(self, lo, hi, x0, x1):
        self.lo, self.hi, self.x0, self.x1 = lo, hi, x0, x1

    def x(self, m):
        return self.x0 + (m - self.lo) * (self.x1 - self.x0) / (self.hi - self.lo)

    def clip(self, m):
        return min(max(m, self.lo), self.hi)

    def ticks(self, step):
        t = (self.lo // step) * step
        if t < self.lo:
            t += step
        out = []
        while t <= self.hi + 1e-9:
            out.append(t)
            t += step
        return out


def nice_step(span, target=6):
    for s in (5, 10, 15, 20, 30, 60, 120, 180, 240, 360, 720):
        if span / s <= target:
            return s
    return 1440
