"""Shared drawing pieces for the animations: the tools/diagrams palette, pixel coordinates, text.

Scenes are laid out in pixels of the 1280x720 frame (origin top left, y down), as the SVG figures
are, and converted to manim units here. Text is Liberation Sans (Helvetica metrics, as the SVG
figures' font stack) and never smaller than MIN_SIZE: manim's font_size 14 draws a capital 12 px
tall at 720p, the cap height of a 17 px CSS font.
"""
import sys
from pathlib import Path

import numpy as np
from manim import (BOLD, DOWN, ITALIC, LEFT, NORMAL, RIGHT, UP, DashedLine, Line, Polygon, Rectangle,
                   RoundedRectangle, Text, VGroup, config)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "diagrams"))
sys.path.insert(0, str(REPO / "tools"))
from svgkit import (BAD, BAD_T, BLUE, BLUE_T, CARD, FAINT, GOOD, GOOD_T, INK, MUTED, ORANGE,  # noqa: E402,F401
                    ORANGE_T, RULE)

FONT = "Liberation Sans"
MIN_SIZE = 14
PX = config.frame_height / 720          # manim units per pixel of the 720p frame
W, H = 1280, 720
config.background_color = CARD


def P(x, y):
    """A pixel position (origin top left) as a manim point."""
    return np.array([(x - W / 2) * PX, (H / 2 - y) * PX, 0.0])


def T(s, size=16, color=INK, bold=False, italic=False):
    """Text drawn at 4x and scaled down, which keeps manim's glyph spacing even at small sizes."""
    if size < MIN_SIZE:
        raise ValueError(f"text below {MIN_SIZE}: {s!r}")
    t = Text(str(s), font=FONT, font_size=size * 4, color=color,
             weight=BOLD if bold else NORMAL, slant=ITALIC if italic else NORMAL)
    return t.scale(0.25)


def width_px(mob):
    return mob.width / PX


def at(mob, x, y, anchor="left"):
    """Place mob with its left edge (or centre, or right edge) at pixel x, vertically centred on y."""
    p = P(x, y)
    if anchor == "left":
        mob.move_to(p, aligned_edge=LEFT)
    elif anchor == "right":
        mob.move_to(p, aligned_edge=RIGHT)
    else:
        mob.move_to(p)
    return mob


def fit(s, size, max_px, **kw):
    """Text no wider than max_px, cut with an ellipsis."""
    t = T(s, size, **kw)
    s = str(s)
    while width_px(t) > max_px and len(s) > 1:
        s = s[:-1]
        t = T(s.rstrip() + "…", size, **kw)
    return t


def wrap(s, size, max_px, **kw):
    """Lines of text, each no wider than max_px, as a VGroup stacked down from the first line."""
    lines, cur = [], ""
    for word in str(s).split():
        cand = (cur + " " + word).strip()
        if cur and width_px(T(cand, size, **kw)) > max_px:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return [T(x, size, **kw) for x in lines]


def text_block(s, x, y, size, max_px, gap=None, **kw):
    """Wrapped text whose first line is centred on y; returns (VGroup, y below the last line)."""
    gap = gap or size * 1.35
    g = VGroup()
    for i, t in enumerate(wrap(s, size, max_px, **kw)):
        g.add(at(t, x, y + i * gap))
    return g, y + gap * len(g)


def box(x0, y0, x1, y1, fill=FAINT, stroke=None, r=6, sw=1.0):
    b = RoundedRectangle(width=(x1 - x0) * PX, height=(y1 - y0) * PX, corner_radius=r * PX,
                         fill_color=fill, fill_opacity=1, stroke_color=stroke or fill,
                         stroke_width=sw if stroke else 0)
    return b.move_to(P((x0 + x1) / 2, (y0 + y1) / 2))


def bar(x0, x1, y, h, fill, stroke):
    b = Rectangle(width=max(x1 - x0, 3) * PX, height=h * PX, fill_color=fill, fill_opacity=1,
                  stroke_color=stroke, stroke_width=1.5)
    return b.move_to(P((x0 + max(x1, x0 + 3)) / 2, y))


def hline(x0, x1, y, color=RULE, sw=1.0):
    return Line(P(x0, y), P(x1, y), color=color, stroke_width=sw)


def vdash(x, y0, y1, color="#9a9a9a", sw=1.5):
    return DashedLine(P(x, y0), P(x, y1), color=color, stroke_width=sw, dash_length=4 * PX)


def tri_right(x, y, color, s=9):
    return Polygon(P(x, y - s / 2), P(x + s, y), P(x, y + s / 2), color=color, fill_color=color,
                   fill_opacity=1, stroke_width=0)


def cross(x, y, color=BAD, r=6, sw=3):
    return VGroup(Line(P(x - r, y - r), P(x + r, y + r), color=color, stroke_width=sw),
                  Line(P(x - r, y + r), P(x + r, y - r), color=color, stroke_width=sw))


def dot(x, y, color=INK, r=5, filled=True):
    from manim import Circle
    c = Circle(radius=r * PX, color=color, stroke_width=2)
    c.set_fill(color if filled else CARD, opacity=1)
    return c.move_to(P(x, y))


def cell(s, x, y, ink=INK, edge=RULE, fill=CARD, size=14, bold=False, max_left=0, max_right=W):
    """A reading in a small box centred at x (kept inside [max_left, max_right])."""
    t = T(s, size, color=ink, bold=bold)
    w = width_px(t) + 16
    cx = min(max(x, max_left + w / 2), max_right - w / 2)
    hh = size / 2 + 6
    b = box(cx - w / 2, y - hh, cx + w / 2, y + hh, fill=fill, stroke=edge, r=4, sw=1.5)
    return VGroup(b, at(t, cx, y, "center"))


class TimeAxis:
    """Minutes (or seconds) mapped to pixel x in [x0, x1]."""

    def __init__(self, lo, hi, x0, x1):
        self.lo, self.hi, self.x0, self.x1 = lo, hi, x0, x1

    def x(self, v):
        return self.x0 + (v - self.lo) * (self.x1 - self.x0) / (self.hi - self.lo)

    def ticks(self, step):
        t = -(-self.lo // step) * step
        out = []
        while t <= self.hi + 1e-9:
            out.append(t)
            t += step
        return out


__all__ = ["BAD", "BAD_T", "BLUE", "BLUE_T", "CARD", "FAINT", "GOOD", "GOOD_T", "INK", "MUTED", "ORANGE",
           "ORANGE_T", "RULE", "P", "T", "at", "fit", "wrap", "text_block", "box", "bar", "hline", "vdash",
           "tri_right", "cross", "dot", "cell", "width_px", "TimeAxis", "REPO", "DOWN", "UP", "LEFT", "RIGHT"]
