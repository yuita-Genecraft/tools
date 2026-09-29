#!/usr/bin/env python3
"""Artifact 用の app.html（骨格なし）から、GitHub Pages などに置ける単体 index.html を作る（共通）。

- doctype / head / body を付ける
- CSP で外部通信を禁止（connect-src 'none' ほか）＝「通信ゼロ」をブラウザ側で強制
- window.__STANDALONE__ = true、window.__TOOL_URL__ = --url
- --url があれば OGP / Twitter カードを付ける（--og は画像のファイル名か、https:// から始まる URL）
使い方: python3 build_standalone.py <app.html> <out.html> [--url URL] [--og og.png]
"""
import argparse, html, json, pathlib, re

CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src data: blob:; connect-src 'none'; font-src 'none'; form-action 'none'; base-uri 'none'")

def build(src: str, url: str = "", og: str = "") -> str:
    cut = src.index("</style>") + len("</style>")
    head_part, body_part = src[:cut], src[cut:]
    title = re.search(r"<title>(.*?)</title>", src, re.S).group(1).strip()
    m = re.search(r'<meta name="description" content="([^"]*)"', src)
    desc = html.unescape(m.group(1)) if m else ""
    og_tags = ""
    if url:
        img = (og if re.match(r"https?://", og) else url.rstrip("/") + "/" + og) if og else ""
        og_tags = "\n".join(t for t in [
            '<meta property="og:type" content="website">',
            f'<meta property="og:title" content="{html.escape(title)}">',
            f'<meta property="og:description" content="{html.escape(desc)}">',
            f'<meta property="og:url" content="{html.escape(url)}">',
            f'<meta property="og:image" content="{html.escape(img)}">' if img else "",
            '<meta name="twitter:card" content="summary_large_image">',
        ] if t)
    boot = f"<script>window.__STANDALONE__=true;window.__TOOL_URL__={json.dumps(url)};</script>"
    return "\n".join(x for x in [
        "<!doctype html>", '<html lang="ja">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">',
        '<meta name="referrer" content="no-referrer">', og_tags, boot, head_part,
        "</head>", "<body>", body_part, "</body>", "</html>", ""] if x != "")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--url", default=""); ap.add_argument("--og", default="")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(pathlib.Path(a.src).read_text(encoding="utf-8"), a.url, a.og), encoding="utf-8")
    print(out, out.stat().st_size, "bytes")
