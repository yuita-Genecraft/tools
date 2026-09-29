#!/usr/bin/env python3
"""OG 画像（1200×630）を作って docs/og/ に置く。Playwright の Chromium を使う。
通知表のカードは、--card で渡した画像（自分のログで出した通知表の PNG）を使い、左に「右は作者の実際の通知表」の注記を出す。
--card を渡さない時は、アプリの見本（#cardImg）をその場で描いて使い、注記は出さない。
og/card.png は作業用で Git には入れない。
使い方: python3 render_og.py [--card 通知表.png] [--note 注記の文]"""
import argparse, base64, pathlib, shutil, sys, tempfile
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from build_standalone import build

PAIRS = [("og/og-tsuchihyo.html", "docs/og/cc-tsuchihyo.png"), ("og/og-fbcheck.html", "docs/og/fbcheck.png")]

ap = argparse.ArgumentParser()
ap.add_argument("--card", help="通知表のカード画像（PNG）。渡すと見本の代わりに使う")
ap.add_argument("--note", default="右は作者の実際の通知表", help="--card の時に左に出す注記")
args = ap.parse_args()

with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
    b = p.chromium.launch()
    # 1) 通知表のカード（og-tsuchihyo.html が card.png として読む）
    card = HERE / "og" / "card.png"
    if args.card:
        shutil.copy(args.card, card)
    else:
        app = pathlib.Path(tmp) / "tsuchihyo.html"
        app.write_text(build((HERE / "cc-tsuchihyo" / "app.html").read_text(encoding="utf-8")), encoding="utf-8")
        page = b.new_page()
        page.goto(app.as_uri())
        page.wait_for_function("document.getElementById('cardImg').src.startsWith('data:image/png')")
        data = page.get_attribute("#cardImg", "src").split(",", 1)[1]
        card.write_bytes(base64.b64decode(data))
    # 2) OG カードを撮る
    page = b.new_page(viewport={"width": 1200, "height": 630})
    for src, out in PAIRS:
        o = HERE / out
        o.parent.mkdir(parents=True, exist_ok=True)
        page.goto((HERE / src).resolve().as_uri())
        if args.card and src == "og/og-tsuchihyo.html":
            page.evaluate("t => { const n = document.getElementById('note'); n.textContent = t; n.hidden = false; }", args.note)
        page.wait_for_timeout(300)
        page.screenshot(path=str(o))
        print(out)
    b.close()
