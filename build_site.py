#!/usr/bin/env python3
"""GitHub Pages 用の docs/ を作る。BASE は公開先の URL（末尾 / あり）。
OG 画像（docs/og/*.png）は消さずに残す。作り直すときは render_og.py。
使い方: python3 build_site.py [BASE]   例: python3 build_site.py https://yuita-genecraft.github.io/tools/"""
import pathlib, shutil, subprocess, sys
HERE = pathlib.Path(__file__).parent
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://yuita-genecraft.github.io/tools/").rstrip("/") + "/"
DOCS = HERE / "docs"
TOOLS = [("cc-tsuchihyo", "cc-tsuchihyo/app.html"), ("fbcheck", "fbcheck-web/app.html")]
DOCS.mkdir(exist_ok=True)
(DOCS / ".nojekyll").write_text("\n")  # 中身は何でもよい（GitHub は有無だけを見る）。空だと一部の送り方で弾かれるので改行1つ
shutil.copy(HERE / "site-src" / "index.html", DOCS / "index.html")
for slug, src in TOOLS:
    shutil.rmtree(DOCS / slug, ignore_errors=True)
    og = DOCS / "og" / f"{slug}.png"
    if not og.exists():
        print(f"注意: {og.relative_to(HERE)} がありません（python3 render_og.py で作る）")
    subprocess.run([sys.executable, str(HERE / "build_standalone.py"), str(HERE / src), str(DOCS / slug / "index.html"),
                    "--url", BASE + slug + "/", "--og", BASE + f"og/{slug}.png"], check=True)
print("docs/ ->", BASE)
