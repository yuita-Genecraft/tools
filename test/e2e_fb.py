#!/usr/bin/env python3
"""Firebase 公開前チェック：ブラウザ版と CLI（同じ engine から作った fbcheck.mjs）を同じ入力で突き合わせ、
セカンドオピニオンで指摘された形（偽PASS・言い過ぎ）が出ないことを個別に確かめる。"""
import json, os, pathlib, re, subprocess, sys
from playwright.sync_api import sync_playwright
HERE = pathlib.Path(__file__).parent; ROOT = HERE.parent
CLI = HERE / "out" / "fbcheck.mjs"   # engine から毎回作る（Git には入れない）
# テスト用プロジェクトの上の階層（このリポジトリ自体）を git が見に行かないようにする。
# これが無いと、git の外のつもりの fbproj〜fbproj5 が、このリポジトリの中として判定される。
CLI_ENV = {**os.environ, "GIT_CEILING_DIRECTORIES": str(HERE.resolve())}
# app.html は直さない（--no-app）：コミットした ENGINE 区間が engine.js とずれていれば、ここで失敗にする（N5）
subprocess.run([sys.executable, str(ROOT / "fbcheck-web/sync_engine.py"), "--no-app", str(CLI)], check=True)
sync = subprocess.run([sys.executable, str(HERE / "check_engine_sync.py"), str(ROOT / "fbcheck-web/app.html")], capture_output=True, text=True)
print(sync.stdout.strip())
if sync.returncode != 0:
    print("NG  app.html の ENGINE 区間が engine.js と違います（python3 fbcheck-web/sync_engine.py で入れ直してコミット）"); sys.exit(1)
subprocess.run([sys.executable, str(ROOT / "build_standalone.py"), str(ROOT / "fbcheck-web/app.html"), str(ROOT / "fbcheck-web/dist/index.html")], check=True)
subprocess.run([sys.executable, str(HERE / "gen_fbproj.py")], check=True)
URL = (ROOT / "fbcheck-web/dist/index.html").as_uri()
SHOTS = HERE / "shots"; SHOTS.mkdir(exist_ok=True)
FIX = ["fbproj", "fbproj2", "fbproj3", "fbproj4", "fbproj5", "fbproj9", "fbproj10", "fbproj11", "fbproj12", "fbproj13", "fbproj14", "fbproj15", "fbproj16", "fbproj17"]          # git の外＝CLI も Git を読めない→ブラウザ版と一致するはず
FIX_GIT = ["fbproj6", "fbproj7", "fbproj8"]                           # 本物の git リポジトリ＝CLI だけが git で確かめられる

def parse_cli(txt):
    lv = None; out = {"danger": [], "warn": [], "info": []}; cur = None; in_ev = False
    for line in txt.splitlines():
        if line.startswith("■ 公開前に直すもの"): lv = "danger"; continue
        if line.startswith("■ 見ておくもの"): lv = "warn"; continue
        if line.startswith("■ 直さなくていいもの"): lv = "info"; continue
        if line.startswith("■"): lv = None; continue
        if lv is None: continue
        m = re.match(r"^(\d+)\. (.+)$", line)
        if m: cur = {"title": m.group(2), "ev": []}; out[lv].append(cur); in_ev = False; continue
        if "根拠（あなたのファイルの実物）" in line: in_ev = True; continue
        if in_ev:
            if line.startswith("     ") and line.strip(): cur["ev"].append(line.strip())
            else: in_ev = False
    return out

fails = 0
def ok(cond, msg):
    global fails
    print(("OK  " if cond else "NG  ") + msg)
    if not cond: fails += 1

WEB = """(() => { const c = window.__fbcheck.current;
  const o = {}; for (const k of ['danger','warn','info']) o[k] = c.res.findings[k].map(f => ({title: f.title, ev: (f.evidence||[]).map(evText)}));
  return o; })()""".replace("evText", "(e => e.loc && e.code != null ? `${e.loc}  ${e.code}` : e.loc ? `${e.loc}${e.note || ''}` : e.note)")

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 1000}, timezone_id="Asia/Tokyo", locale="ja-JP", bypass_csp=True)
    page = ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e))); page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.goto(URL); page.wait_for_function("window.__fbcheck && window.__fbcheck.current")
    page.screenshot(path=str(SHOTS / "fb-sample-desktop-light.png"), full_page=True)
    sample = page.evaluate(WEB)
    print("sample:", json.dumps({k: [f["title"] for f in v] for k, v in sample.items()}, ensure_ascii=False))
    res = {}
    for proj in FIX:
        page.set_input_files("#dirInput", str(HERE / proj))
        page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのプロジェクト'", timeout=30000)
        web = page.evaluate(WEB); res[proj] = web
        cli = parse_cli(subprocess.run(["node", str(CLI), str(HERE / proj)], capture_output=True, text=True, env=CLI_ENV).stdout)
        same = all([(f["title"], f["ev"]) for f in web[k]] == [(f["title"], f["ev"]) for f in cli[k]] for k in ("danger", "warn", "info"))
        ok(same, f"{proj}: ブラウザ版と CLI が一致（直す{len(web['danger'])}・見る{len(web['warn'])}・誤解{len(web['info'])}）")
        if not same: print("   web:", json.dumps(web, ensure_ascii=False)[:600]); print("   cli:", json.dumps(cli, ensure_ascii=False)[:600])
        page.click("#againBtn"); page.wait_for_function("document.getElementById('statusPill').textContent === '見本'")
    for proj in FIX_GIT:
        page.set_input_files("#dirInput", str(HERE / proj))
        page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのプロジェクト'", timeout=30000)
        res[proj] = page.evaluate(WEB)
        page.click("#againBtn"); page.wait_for_function("document.getElementById('statusPill').textContent === '見本'")
    page.set_input_files("#dirInput", str(HERE / "fbproj4")); page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのプロジェクト'")
    page.screenshot(path=str(SHOTS / "fb-mine-fbproj4.png"), full_page=True)
    print("page errors:", errs)
    b.close()

allf = lambda r: [f for k in ("danger", "warn", "info") for f in r[k]]
cli = {p_: parse_cli(subprocess.run(["node", str(CLI), str(HERE / p_)], capture_output=True, text=True, env=CLI_ENV).stdout) for p_ in FIX_GIT}
r4, r5, r1 = res["fbproj4"], res["fbproj5"], res["fbproj"]
UNCONF = ".env が Git で追跡済みかは、ここでは確かめられません"
NOPAT = ".gitignore に除外する行が見つからない .env ファイルがあります"
envf = lambda r, title: [f for k in ("danger", "warn") for f in r[k] if f["title"] == title]
# BLOCK1（前回）: .gitignore=.env だけ → .env.production / .env.local は「除外の行なし」、.env は「未確認」
np4 = envf(r4, NOPAT); un4 = envf(r4, UNCONF)
ok(len(np4) == 1 and {e.split("（")[0] for e in np4[0]["ev"]} == {".env.local", ".env.production"}, "前回BLOCK1: .gitignore=.env → .env.production/.env.local を「除外の行なし」で出す")
ok(len(un4) == 1 and un4[0] in r4["warn"] and un4[0]["ev"][0].startswith(".env（"), "前回BLOCK1: .env は除外済みと言わず「未確認」で出す")
# 今回BLOCK: ブラウザ版は Git の状態を読めない → 「除外済み」と言わない（未確認で出す）。黙って通さない
for p_, want in (("fbproj5", {".env.production", "apps/web/.env"}), ("fbproj6", {".env"}), ("fbproj7", {"apps/web/.env"}), ("fbproj8", {".env"})):
    u = envf(res[p_], UNCONF)
    ok(len(u) == 1 and u[0] in res[p_]["warn"] and {e.split("（")[0] for e in u[0]["ev"]} == want, f"今回BLOCK（ブラウザ）: {p_} は「未確認」で出す（黙って通さない）")
ok(any("鍵らしき値あり：OpenAI APIキー" in e for f in envf(res["fbproj6"], UNCONF) for e in f["ev"]), "今回BLOCK（ブラウザ）: 追跡済みかもしれない .env の鍵も見せる")
# 今回BLOCK: CLI は git 自身で確かめる
c6 = [f for f in cli["fbproj6"]["danger"] if f["title"] == "Git で追跡されている .env ファイルがあります"]
ok(len(c6) == 1 and c6[0]["ev"] == [".env（Git で追跡中・鍵らしき値あり：OpenAI APIキー）"], "今回BLOCK（CLI）: コミット済み .env＋あとから .env* → 追跡中として危険に出す")
c7 = [f for f in cli["fbproj7"]["danger"] if f["title"] == "Git の管理から外れていない .env ファイルがあります"]
ok(len(c7) == 1 and c7[0]["ev"] == ["apps/web/.env（git check-ignore で除外されていない）"], "今回BLOCK（CLI）: 下の階層の !.env で打ち消し → 除外されていないと出す")
ok(not any(".env" in f["title"] for f in allf(cli["fbproj8"])), "今回BLOCK（CLI）: 追跡していない＋.env* で除外 → 何も出さない")
# 前回BLOCK2・REVIEW
read_only = [f for f in allf(r4) if any("allow read: if true;" in e for e in f["ev"])]
ok(len(read_only) == 1 and "読み書き" not in read_only[0]["title"] and "読める" in read_only[0]["title"], "前回BLOCK2: allow read: if true を読み書きと言わない")
ok(any(f["title"].startswith("誰でも読み書きできる状態です") for f in r1["danger"]), "前回BLOCK2: allow read, write: if true は読み書きと出す")
auth4 = [f for f in allf(r4) if any("request.auth != null;" in e for e in f["ev"])]
ok(len(auth4) == 1 and auth4[0] in r4["warn"] and "他人のデータ" not in auth4[0]["title"], "前回REVIEW: 共有データの auth だけの許可は「見ておく」で、断定しない")
ok(any(f["title"].startswith("ログインすれば、すべての文書を読み書きできます") for f in r5["danger"]), "前回REVIEW: {document=**} に効く auth だけの許可は「直す」")
tm4 = [f for f in allf(r4) if "無認証" in f["title"]]
ok(len(tm4) == 1 and "firestore.rules:13" in tm4[0]["ev"][0], "前回REVIEW: 関係ない timestamp.date は拾わない（logs の1件だけ）")
tm_all = [f for p_ in res.values() for f in allf(p_) if "無認証" in f["title"]]
ok(tm_all and all("（Firebase のテストモードと同じ形・" in f["title"] and not f["title"].startswith("テストモード") for f in tm_all), "今回REVIEW: 見出しは「期限まで無認証で許可するルール（Firebase のテストモードと同じ形）」")
ok(any(f["title"].startswith("期限切れの無認証許可ルール") for f in r1["warn"]), "今回REVIEW: 期限切れは「期限切れの無認証許可ルール」")
# 判定の直し（fbcheck-review v0.1）：実際の画面（ブラウザ版）と CLI が同じ結果で、無言の allow が無いこと（N5 は上の一致の確認）
r9, r10, r11, r12 = res["fbproj9"], res["fbproj10"], res["fbproj11"], res["fbproj12"]
t9 = lambda r, k: [f["title"] for f in r[k]]
ok("誰でも読み書きできる状態です（firestore.rules）" in t9(r9, "danger"), "N1: allow read, write;（条件なし）を danger で出す")
ok("誰でも読める状態です（storage.rules）" in t9(r9, "danger") and any(x.startswith("ログインすれば、すべてのファイルを書き込めます") for x in t9(r9, "danger")), "B1: Storage の allow read; と write の auth の両方を出す")
un9 = [f for f in r9["warn"] if f["title"].startswith("判定できなかった allow の行があります")]
ok(len(un9) == 1 and un9[0]["title"].startswith("判定できなかった allow の行があります（1 行") and any("isSignedIn()" in e for e in un9[0]["ev"]) and not any("request.auth.uid == userId" in e for e in un9[0]["ev"]), "N2: 関数の allow を行の実物つきで出す（無言にしない）。持ち主の定番の形（auth != null && uid == userId）は読めるので出さない。次の行に続く条件（allow write: if ⏎ request.auth != null;）は、つないで読んで判定する")
ok(any(x.startswith("ログインすれば、すべての文書を") or x.startswith("ログインしている人なら誰でも") for x in t9(r9, "danger") + t9(r9, "warn")), "N2: 次の行に続く条件を、つないで読んで auth と判定する")
ok(not any("request.auth.uid == userId" in e for f in r9["danger"] + r9["info"] for e in f["ev"]), "B8: 持ち主のルールの行を danger にしない（&& を含むので「判定できなかった行」に出る）")
ok(any(x.startswith("期限まで無認証で許可するルール") and "Realtime Database" in x for x in t9(r10, "danger")), "B5: コメント入り・末尾カンマの RTDB（now < 期限内）を読んで danger")
ok(any(x.startswith("ログインしている人なら誰でも読める場所があります（Realtime Database") for x in t9(r10, "warn")), "B5: RTDB の一部の auth != null を warn")
ok(t9(r12, "warn") == ["database.rules.json を読めませんでした"] and t9(r12, "danger") == [] , "N4: 壊れた RTDB の JSON は warn（無言にしない）・danger にもしない")
g11 = [f for f in r11["danger"] if f["title"] == "Gemini のキーがブラウザ側に出ています"]
ok(len(g11) == 1 and {e.split(" ")[0] for e in g11[0]["ev"]} == {"src/ai.ts:2", ".env:1"}, "B4: Gemini の痕跡＋AIza（src と接頭辞つき .env）を出し、firebaseConfig・VITE_FIREBASE_API_KEY は含めない")
ok(len(r11["info"]) == 1 and r11["info"][0]["ev"] == ["src/firebase.ts:3（対応不要）"], "B4: firebaseConfig の apiKey は従来どおり info")
ok(not any(f["title"].startswith("Gemini") for f in allf(r12)) and len(r12["info"]) == 1, "N3: Gemini の痕跡が無い apiKey は danger にしない（info のまま）")
g13 = res["fbproj13"]
ok(any(f["title"].startswith("ログインしている人なら誰でも読める場所があります") and f["ev"][0].startswith("firestore.rules:3") for f in g13["warn"]), "N5/B3: #02 request.auth.uid != null を auth と同じに読む（ブラウザ版と CLI が一致）")
u13 = [f for f in g13["warn"] if f["title"].startswith("判定できなかった allow の行があります")]
ok(len(u13) == 1 and u13[0]["title"].startswith("判定できなかった allow の行があります（4 行") , "N5/N2: #03・#06・&& の関数・true && true を無言にしない（4 行）。複数行の ops と持ち主の定番の形は読める")
ok(not any("true && true" in e for f in g13["danger"] for e in f["ev"]) and any("true && true" in e for f in u13 for e in f["ev"]), "B2: if true && true は && を含むので danger ではなく判定できなかった行（全体がちょうど true の時だけ true）")
g14 = res["fbproj14"]
ok(len([f for f in g14["danger"] if f["title"] == "Gemini のキーがブラウザ側に出ています"][0]["ev"]) == 2 and len(g14["info"]) == 1 and g14["info"][0]["ev"] == ["src/firebase.ts:2（対応不要）"], "B4: firebaseConfig の隣・同じ行の Gemini キーを見逃さず、Firebase の鍵だけ info")
ok(t9(res["fbproj15"], "warn") == ["database.rules.json を読めませんでした"], "N4: 閉じていない /* の database.rules.json は warn（無言にしない）")
g16 = res["fbproj16"]
ok(not any(f["title"].startswith("ログインすれば、すべての文書を読み書きできます") for f in g16["danger"]) and any("true && request.auth != null" in e for f in g16["warn"] if f["title"].startswith("判定できなかった") for e in f["ev"]), "r2-1: true && request.auth != null は && を含むので danger にせず、判定できなかった行に出す")
gm16 = [f for f in g16["danger"] if f["title"] == "Gemini のキーがブラウザ側に出ています"]
ok(len(gm16) == 1 and [e.split(" ")[0] for e in gm16[0]["ev"]] == ["src/ai.ts:1"] and g16["info"] == [], "r2-2/3: 値の文字列に authDomain があるだけの Gemini だけを danger にし、長い空白をはさんだ firebaseConfig の鍵は Gemini にしない（info は同じ行に鍵が無いので出ない）")
g17 = res["fbproj17"]
w17 = [f for f in g17["warn"] if f["title"] == "Firebase の設定か Gemini のキーか判定できなかった AIza… があります"]
ok(len(w17) == 1 and [e.split(" ")[0] for e in w17[0]["ev"]] == ["src/b.ts:2"] and not [f for f in g17["danger"] if f["title"].startswith("Gemini")], "r3: 正規表現リテラルで読み切れないファイルは warn（行の実物つき）・コメントをはさんだ firebaseConfig は Firebase の鍵・どちらも danger にしない")
print("\nALL PASS" if fails == 0 else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
