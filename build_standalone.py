#!/usr/bin/env python3
"""Artifact 用の app.html（骨格なし）から、GitHub Pages などに置ける単体 index.html を作る（共通）。

- doctype / head / body を付ける
- CSP で外部通信を禁止（connect-src 'none' ほか）＝「通信ゼロ」をブラウザ側で強制
- window.__STANDALONE__ = true、window.__TOOL_URL__ = --url
- --url があれば OGP / Twitter カードを付ける（--og は画像のファイル名か、https:// から始まる URL）
使い方: python3 build_standalone.py <app.html> <out.html> [--url URL] [--og og.png]
"""
import argparse, html, json, pathlib, re

def inline_scripts(src: str, source_dir: pathlib.Path) -> str:
    """Embed explicit sibling JS assets; the built page keeps its no-network CSP."""
    def replace(m):
        code = (source_dir / m.group(1)).read_text(encoding="utf-8")
        # An HTML parser ends a script even inside a JS string/comment.
        code = re.sub(r"</script", r"<\\/script", code, flags=re.I)
        return "<script>\n" + code + "\n</script>"
    src = re.sub(r'<script data-embed="([A-Za-z0-9_-]+\.js)"></script>', replace, src)
    def css(m):
        code = (source_dir / m.group(1)).read_text(encoding="utf-8")
        if re.search(r"</style", code, re.I):
            raise ValueError("Embedded CSS must not contain a closing style tag")
        return code
    return re.sub(r'/\* @embed ([A-Za-z0-9_-]+\.css) \*/', css, src)

CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src data: blob:; connect-src 'none'; font-src {font}; form-action 'none'; base-uri 'none'")

def build(src: str, url: str = "", og: str = "") -> str:
    csp = CSP.format(font="data:" if "data:font/" in src else "'none'")   # 書体を埋め込んだページだけ data: の font を許す（通信は変わらず無し）
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
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">',
        '<meta name="referrer" content="no-referrer">', og_tags, boot, head_part,
        "</head>", "<body>", body_part, "</body>", "</html>", ""] if x != "")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--url", default=""); ap.add_argument("--og", default="")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    source = pathlib.Path(a.src)
    out.write_text(build(inline_scripts(source.read_text(encoding="utf-8"), source.parent), a.url, a.og), encoding="utf-8")
    print(out, out.stat().st_size, "bytes")
