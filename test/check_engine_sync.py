#!/usr/bin/env python3
"""fbcheck repo の fbcheck.mjs（ENGINE 区間）が、このリポジトリの fbcheck-web/engine.js と同じ文字列かを調べる。
使い方: python3 test/check_engine_sync.py <fbcheck.mjs のパス>   一致なら 0・違えば 1（fbcheck repo への同期が要る：sync_engine.py）"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
eng = (ROOT / "fbcheck-web/engine.js").read_text(encoding="utf-8").rstrip("\n")
s = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
b = s.find("/* ENGINE:BEGIN"); e = s.find("/* ENGINE:END */")
if b < 0 or e < 0:
    print("NG  fbcheck.mjs に ENGINE の区間が見つかりません"); sys.exit(1)
got = s[b:e + len("/* ENGINE:END */")]
if got == eng:
    print("OK  fbcheck repo の fbcheck.mjs の ENGINE 区間は engine.js と同じです"); sys.exit(0)
ver = lambda t: next((l.strip() for l in t.splitlines() if l.startswith("const FBCHECK_VERSION")), "?")
print(f"NG  ENGINE 区間が engine.js と違います（repo 側 {ver(got)} / ここ {ver(eng)}）。python3 fbcheck-web/sync_engine.py で fbcheck.mjs を作り直し、fbcheck repo へ PR を出してください")
sys.exit(1)
