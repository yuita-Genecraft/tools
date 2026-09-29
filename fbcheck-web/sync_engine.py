#!/usr/bin/env python3
"""engine.js（判定本体）を、ブラウザ版 app.html と CLI（fbcheck.mjs）に同じ文字列で入れる。
使い方: python3 sync_engine.py <CLIの出力先 fbcheck.mjs>"""
import pathlib, re, sys
HERE = pathlib.Path(__file__).parent
eng = (HERE / "engine.js").read_text(encoding="utf-8").rstrip("\n")
app = HERE / "app.html"
s = app.read_text(encoding="utf-8")
b = s.index("/* ENGINE:BEGIN"); e = s.index("/* ENGINE:END */") + len("/* ENGINE:END */")
s2 = s[:b] + eng + s[e:]
if s2 != s:
    app.write_text(s2, encoding="utf-8"); print("app.html: engine updated")
else:
    print("app.html: engine already in sync")
if len(sys.argv) > 1:
    tpl = (HERE / "cli.template.mjs").read_text(encoding="utf-8")
    assert tpl.count("/* ENGINE */") == 1
    out = pathlib.Path(sys.argv[1]); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tpl.replace("/* ENGINE */", eng), encoding="utf-8")
    print("cli:", out)
