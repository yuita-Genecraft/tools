#!/usr/bin/env python3
"""engine.js（判定本体）を、ブラウザ版 app.html と CLI（fbcheck.mjs）に同じ文字列で入れる。
使い方: python3 sync_engine.py [--no-app] <CLIの出力先 fbcheck.mjs>
  --no-app：app.html は書き換えない（試験で、コミット済みの app.html の ENGINE 区間が engine.js とずれていないかを見る時）"""
import pathlib, re, sys
HERE = pathlib.Path(__file__).parent
eng = (HERE / "engine.js").read_text(encoding="utf-8").rstrip("\n")
args = [a for a in sys.argv[1:] if a != "--no-app"]
no_app = len(args) != len(sys.argv) - 1
app = HERE / "app.html"
s = app.read_text(encoding="utf-8")
b = s.index("/* ENGINE:BEGIN"); e = s.index("/* ENGINE:END */") + len("/* ENGINE:END */")
s2 = s[:b] + eng + s[e:]
if no_app:
    print("app.html: not touched (--no-app)")
elif s2 != s:
    app.write_text(s2, encoding="utf-8"); print("app.html: engine updated")
else:
    print("app.html: engine already in sync")
if args:
    tpl = (HERE / "cli.template.mjs").read_text(encoding="utf-8")
    assert tpl.count("/* ENGINE */") == 1
    out = pathlib.Path(args[0]); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tpl.replace("/* ENGINE */", eng), encoding="utf-8")
    print("cli:", out)
