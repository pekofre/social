"""Render a Peko .dc.html artboard with CSS animations to an MP4, frame by frame.

Usage:
  python3 motion.py <artboard.dc.html> <assets_dir> <motion.css> <out.mp4> [seconds=6] [fps=30]

The artboard is built exactly like render.py builds it (theme, {{holes}}, /_blob/ assets), then
motion.css is added. Every CSS animation is paused and stepped to each frame's time, so the video is
deterministic (no dropped frames). Also writes <out>.poster.png: the last frame, all elements in.
Needs ffmpeg on PATH.
"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import JS, build  # noqa: E402


async def main():
    src, assets_dir, css_path, out = sys.argv[1:5]
    seconds = float(sys.argv[5]) if len(sys.argv) > 5 else 6.0
    fps = int(sys.argv[6]) if len(sys.argv) > 6 else 30
    w, h = 1080, 1350
    inner, code, props = build(src, assets_dir)
    css = open(css_path, encoding="utf-8").read()
    frames = tempfile.mkdtemp(prefix="motion-")
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch(args=["--allow-file-access-from-files"])
            pg = await b.new_page(viewport={"width": w, "height": h})
            blank = os.path.join(os.path.abspath(assets_dir), "_blank.html")
            with open(blank, "w", encoding="utf-8") as f:
                f.write('<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"></head><body style="margin:0"></body></html>')
            await pg.goto("file://" + blank)
            left = await pg.evaluate(JS, [inner, code, props])
            if left:
                raise SystemExit(f"unresolved hole {left}")
            await pg.add_style_tag(content=css)
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(300)
            await pg.evaluate("document.getAnimations().forEach(a => a.pause())")
            total = int(round(seconds * fps))
            for i in range(total):
                t = i * 1000 / fps
                await pg.evaluate(f"document.getAnimations().forEach(a => {{ a.currentTime = {t}; }})")
                await pg.screenshot(path=os.path.join(frames, f"f{i:04d}.png"), clip={"x": 0, "y": 0, "width": w, "height": h})
            await b.close()
        last = sorted(os.listdir(frames))[-1]
        shutil.copy(os.path.join(frames, last), out.rsplit(".", 1)[0] + ".poster.png")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(frames, "f%04d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "18", "-movflags", "+faststart", out],
            check=True,
        )
    finally:
        shutil.rmtree(frames, ignore_errors=True)


asyncio.run(main())
