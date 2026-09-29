#!/usr/bin/env python3
"""OG 画像（1200×630）を作って docs/og/ に置く。Playwright の Chromium を使う。
通知表のカードは、アプリの見本（#cardImg）をその場で描いて使う（og/card.png は作業用で Git には入れない）。
使い方: python3 render_og.py"""
import base64, pathlib, sys, tempfile
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from build_standalone import build

PAIRS = [("og/og-tsuchihyo.html", "docs/og/cc-tsuchihyo.png"), ("og/og-fbcheck.html", "docs/og/fbcheck.png")]

with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
    b = p.chromium.launch()
    # 1) 通知表の見本カードを描く（og-tsuchihyo.html が card.png として読む）
    app = pathlib.Path(tmp) / "tsuchihyo.html"
    app.write_text(build((HERE / "cc-tsuchihyo" / "app.html").read_text(encoding="utf-8")), encoding="utf-8")
    page = b.new_page()
    page.goto(app.as_uri())
    page.wait_for_function("document.getElementById('cardImg').src.startsWith('data:image/png')")
    data = page.get_attribute("#cardImg", "src").split(",", 1)[1]
    (HERE / "og" / "card.png").write_bytes(base64.b64decode(data))
    # 2) OG カードを撮る
    page = b.new_page(viewport={"width": 1200, "height": 630})
    for src, out in PAIRS:
        o = HERE / out
        o.parent.mkdir(parents=True, exist_ok=True)
        page.goto((HERE / src).resolve().as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=str(o))
        print(out)
    b.close()
