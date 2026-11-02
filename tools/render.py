"""Render a Peko .dc.html artboard to a PNG, the way the Design canvas shows it.

Usage:
  python3 render.py <artboard.dc.html> <assets_dir> <out.png> [theme] [width] [height]

<assets_dir> holds the artboard's /_blob/ assets saved as files named by asset id
(any extension), e.g. 3e3a8295cc7725d2636006052c5cef20.otf. The fonts are NOT
part of this public repo: download them from the template canvas each run.

theme: optional override of the "theme" tweak; otherwise its data-props default
(or the value already set in the file) is used.
"""
import asyncio
import json
import os
import re
import sys

from playwright.async_api import async_playwright


def build(src, assets_dir):
    t = open(src, encoding="utf-8").read()
    m = re.search(r"data-props='(.*?)'", t, re.S)
    props_def = json.loads(m.group(1).replace("&#39;", "'").replace("&amp;", "&")) if m else {}
    defaults = {k: v["default"] for k, v in props_def.items() if isinstance(v, dict) and "default" in v}
    code = re.search(r'<script type="text/x-dc"[^>]*>(.*?)</script>', t, re.S).group(1)
    inner = re.search(r"<x-dc>(.*?)</x-dc>", t, re.S).group(1)
    inner = inner.replace("<helmet>", "").replace("</helmet>", "")
    files = {os.path.splitext(f)[0]: f for f in os.listdir(assets_dir)}

    def blob(mm):
        aid = mm.group(1)
        if aid not in files:
            raise SystemExit(f"missing asset {aid} in {assets_dir}")
        return "file://" + os.path.join(os.path.abspath(assets_dir), files[aid])

    inner = re.sub(r"/_blob/([0-9a-f]{32})", blob, inner)
    return inner, code, defaults


JS = r"""
([inner, code, props]) => {
  class DCLogic { constructor(p){ this.props = p; this.state = {}; } setState(){} forceUpdate(){} }
  const Component = new Function('DCLogic', code + '\nreturn Component;')(DCLogic);
  const vals = new Component(props).renderVals() || {};
  const look = (path) => path.trim().split('.').reduce((o, k) => (o == null ? o : o[k]), vals);
  // sc-if: keep or drop blocks
  inner = inner.replace(/<sc-if value="\{\{([^}]+)\}\}"[^>]*>([\s\S]*?)<\/sc-if>/g, (_, p, body) => look(p) ? body : '');
  inner = inner.replace(/\{\{([^}]+)\}\}/g, (_, p) => { const v = look(p); return v == null ? '' : String(v); });
  document.body.innerHTML = inner;
  const left = document.body.innerHTML.match(/\{\{[^}]+\}\}/);
  return left ? left[0] : null;
}
"""


async def main():
    src, assets_dir, out = sys.argv[1:4]
    theme = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
    w = int(sys.argv[5]) if len(sys.argv) > 5 else 1080
    h = int(sys.argv[6]) if len(sys.argv) > 6 else 1350
    inner, code, props = build(src, assets_dir)
    if theme:
        props["theme"] = theme
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
        await pg.evaluate("document.fonts.ready")
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=out, clip={"x": 0, "y": 0, "width": w, "height": h})
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
