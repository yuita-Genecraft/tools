#!/usr/bin/env python3
"""OG 画像（1200×630）を作って docs/og/ に置く。Playwright の Chromium を使う。
通知表のカードは、--card で渡した画像（自分のログで出した通知表の PNG）を使い、左に「右は作者の実際の通知表」の注記を出す。
--card を渡さない時は、アプリの見本（#cardImg）をその場で描いて使い、注記は出さない。
生存率のカードは、アプリの見本（#cardImg）をその場で描いて使う。
og/card.png・og/card-seizon.png は作業用で Git には入れない。
--only <slug> で1枚だけ作り直す（他の PNG に触らない）。
使い方: python3 render_og.py [--card 通知表.png] [--note 注記の文] [--only cc-tsuchihyo|fbcheck|cc-seizon]"""
import argparse, base64, pathlib, shutil, sys, tempfile
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from build_standalone import build

PAIRS = [("cc-tsuchihyo", "og/og-tsuchihyo.html", "docs/og/cc-tsuchihyo.png"), ("fbcheck", "og/og-fbcheck.html", "docs/og/fbcheck.png"), ("cc-seizon", "og/og-seizon.html", "docs/og/cc-seizon.png")]

ap = argparse.ArgumentParser()
ap.add_argument("--card", help="通知表のカード画像（PNG）。渡すと見本の代わりに使う")
ap.add_argument("--note", default="右は作者の実際の通知表", help="--card の時に左に出す注記")
ap.add_argument("--only", help="この slug だけ作り直す")
args = ap.parse_args()
pairs = [p for p in PAIRS if not args.only or p[0] == args.only]

def sample_card(b, app_dir, out, tmp):
    # アプリの見本カード（#cardImg）を PNG にする
    app = pathlib.Path(tmp) / (app_dir + ".html")
    app.write_text(build((HERE / app_dir / "app.html").read_text(encoding="utf-8")), encoding="utf-8")
    page = b.new_page()
    page.goto(app.as_uri())
    page.wait_for_function("document.getElementById('cardImg').src.startsWith('data:image/png')")
    data = page.get_attribute("#cardImg", "src").split(",", 1)[1]
    out.write_bytes(base64.b64decode(data))
    page.close()

with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
    b = p.chromium.launch()
    # 1) 通知表のカード（og-tsuchihyo.html が card.png として読む）
    if any(s == "cc-tsuchihyo" for s, _, _ in pairs):
        card = HERE / "og" / "card.png"
        if args.card:
            shutil.copy(args.card, card)
        else:
            sample_card(b, "cc-tsuchihyo", card, tmp)
    # 2) 生存率のカード（og-seizon.html が card-seizon.png として読む）
    if any(s == "cc-seizon" for s, _, _ in pairs):
        sample_card(b, "cc-seizon", HERE / "og" / "card-seizon.png", tmp)
    # 3) OG カードを撮る
    page = b.new_page(viewport={"width": 1200, "height": 630})
    for slug, src, out in pairs:
        o = HERE / out
        o.parent.mkdir(parents=True, exist_ok=True)
        page.goto((HERE / src).resolve().as_uri())
        if args.card and slug == "cc-tsuchihyo":
            page.evaluate("t => { const n = document.getElementById('note'); n.textContent = t; n.hidden = false; }", args.note)
        page.wait_for_timeout(300)
        page.screenshot(path=str(o))
        print(out)
    b.close()
