#!/usr/bin/env python3
"""Render the animations into docs/30-design/platform/animations/: <name>.webm, <name>.png, <name>.sources.json.

    python tools/animations/render.py --media-dir /tmp/manim-media [name ...]

Needs manim (0.20) and PyAV. manim renders each scene losslessly (QuickTime RLE, 1280x720, 30 fps)
into --media-dir, which must be outside the repository so manim's cache never lands in it; this
script then encodes VP9 once (crf 32, keyframe at most every 10 s), and renders the last frame with
`manim -s` as the poster. The sidecar records the sha256 of the scene and every input at render
time (sources.py); test_animations.py fails when any of them has changed since.

Refuses a video over 2 MB, or a set over 10 MB.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sources import ANIMATIONS, OUT, REPO, manifest, sidecar  # noqa: E402

MAX_ONE, MAX_ALL = 2 * 1024 * 1024, 10 * 1024 * 1024
CRF = "32"


def manim(args, media):
    exe = os.environ.get("MANIM") or shutil.which("manim")
    if not exe:
        raise SystemExit("manim not found: set MANIM=/path/to/manim")
    cmd = [exe, "-qm", "--disable_caching", "--media_dir", str(media)] + args
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout[-4000:] + r.stderr[-4000:])
        raise SystemExit(f"manim failed: {' '.join(args)}")


def encode(src, dst):
    import av
    inp = av.open(str(src))
    vs = inp.streams.video[0]
    rate = int(round(float(vs.average_rate)))
    out = av.open(str(dst), "w", format="webm")
    st = out.add_stream("libvpx-vp9", rate=rate, options={
        "crf": CRF, "b": "0", "row-mt": "1", "deadline": "good", "cpu-used": "2", "g": str(rate * 10)})
    st.width, st.height, st.pix_fmt = vs.width, vs.height, "yuv420p"
    n = 0
    for f in inp.decode(vs):
        g = f.reformat(format="yuv420p")
        g.pts, g.time_base = n, Fraction(1, rate)
        g.pict_type = av.video.frame.PictureType.NONE   # the source marks every RLE frame a keyframe
        for p in st.encode(g):
            out.mux(p)
        n += 1
    for p in st.encode():
        out.mux(p)
    out.close()
    return n / rate


def render(name, media):
    a = ANIMATIONS[name]
    stem = Path(a["scene"]).stem
    manim(["--format", "mov", a["scene"], a["class"]], media)
    mov = media / "videos" / stem / "720p30" / f"{a['class']}.mov"
    OUT.mkdir(parents=True, exist_ok=True)
    seconds = encode(mov, OUT / f"{name}.webm")
    manim(["-s", "--format", "png", a["scene"], a["class"]], media)
    png = media / "images" / stem / f"{a['class']}_ManimCE_v{manim_version()}.png"
    shutil.copyfile(png, OUT / f"{name}.png")
    sidecar(name).write_text(json.dumps(manifest(name), indent=2) + "\n")
    size = (OUT / f"{name}.webm").stat().st_size
    print(f"{name}: {seconds:.1f} s, {size / 1024:.0f} KiB webm, {(OUT / f'{name}.png').stat().st_size / 1024:.0f} KiB png")
    if size > MAX_ONE:
        raise SystemExit(f"{name}.webm is {size} bytes, over {MAX_ONE}")


def manim_version():
    import manim as m
    return m.__version__


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--media-dir", required=True, type=Path)
    ap.add_argument("names", nargs="*")
    args = ap.parse_args()
    media = args.media_dir.resolve()
    if media == REPO or REPO in media.parents:
        raise SystemExit("--media-dir must be outside the repository")
    for name in args.names or list(ANIMATIONS):
        render(name, media)
    total = sum((OUT / f"{n}.webm").stat().st_size for n in ANIMATIONS if (OUT / f"{n}.webm").exists())
    print(f"total webm: {total / 1024:.0f} KiB")
    if total > MAX_ALL:
        raise SystemExit(f"animations total {total} bytes, over {MAX_ALL}")


if __name__ == "__main__":
    main()
