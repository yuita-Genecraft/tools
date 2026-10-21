#!/usr/bin/env python3
"""生存率を Chromium で開いて、見本表示・ログとフォルダの投入・集計値の突き合わせ（Python の別実装＋手で数えた期待値）・
厳密モードの切り替え・CSP を効かせた状態の動作・外部通信ゼロ・横はみ出し無し、までを通す。"""
import base64, json, pathlib, subprocess, sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
APP = HERE.parent / "cc-seizon"
SHOTS = HERE / "shots"
SHOTS.mkdir(exist_ok=True)
subprocess.run([sys.executable, str(HERE.parent / "build_standalone.py"), str(APP / "app.html"), str(APP / "dist" / "index.html")], check=True)
subprocess.run([sys.executable, str(HERE / "gen_seizon.py")], check=True)
sys.path.insert(0, str(HERE))
import ref_seizon  # noqa

URL = (APP / "dist" / "index.html").as_uri()
LOGS = HERE / "seizon" / "logs"
PROJ = HERE / "seizon" / "proj" / "alpha"
log_files = sorted(LOGS.rglob("*.jsonl"))
expect = {False: ref_seizon.run(log_files, PROJ, strict=False), True: ref_seizon.run(log_files, PROJ, strict=True)}

# 手で数えた期待値（gen_seizon.py のコメントと対応）。別実装と同じ間違いをしていないかの歯止め
HAND = {
    # human=6 のうち 4 は gone.ts（ファイルごと消えた）＝dropped。gone.ts に Claude が書いた 5 行＝droppedWritten。急所（top）は今もあるファイルだけ
    # re.ts：s1 が RE・RE2 を書いて RE2 を自分で消し、s2 が RE2 を入れ直した＝written 28（RE は s1・RE2 は s2）・どちらも残っている（alive +2）。rewritten は 3 のまま（入れ直した行は s2 の行になる）
    False: dict(written=28, alive=19, rewritten=3, human=6, dropped=4, droppedWritten=5, aiLines=19, projectLines=37, projectFiles=12, edits=14, sessions=2,
                otherProjectFiles=2, rootCandidates=2, rootMatched=9, uses=21, logFiles=4, logBad=1, root="/Users/t/dev/alpha",
                period={"start": "2026-09-01", "end": "2026-09-05", "days": 5},
                top=[("src/a.ts", 1, 6, True), ("src/c.ts", 1, 3, True)],
                examples={"alive": ("return db.notes.where({ userId }).sortBy('updatedAt');", "src/a.ts"),
                          "human": ("return list.reduce((x, y) => x + y, 0);", "src/c.ts")},
                # 頼み方：s1＝14通×100＝1,400（m2・m5 は2行に分かれているが応答は1つ）・22行書いて13行残存（消えた9行）→ 今は無い分 1,400×9/22=573・残った1行あたり 1,400/13=108
                #         s2＝7通×300＝2,100・alpha に6行（RE2 の入れ直しを含む）＋別の場所に1行（decoy）＝按分 6/7 → 1,800・全部残存 → 0・1行あたり 300
                #         再開で写った s1 の2行（s2.jsonl の先頭）は uuid で重複を除く＝s1 は 14 通のまま。20行以上書いたのは s1 だけ＝高くて消えた・安くて残ったは無し（残存 59%）
                sessionStats=dict(outTotal=3200, outGone=573, costly=["s1"], cheap=[],
                                  rows=[("s2", "引き継ぎ：win.ts・sec.ts・d.ts を足す。範囲外は触らない", 2100, 1800, 7, 4, 6, 6, 0, 0, 0, 300, "2026-09-03", "2026-09-05"),   # s2 の写しは sessionId が s1 のまま＝別の会話のまま（本物の再開は habits の h5 で試す）
                                        ("s1", "a.ts に listNotes を足して、並びは updatedAt にして", 1400, 1400, 14, 10, 22, 13, 3, 2, 4, 108, "2026-09-01", "2026-09-01")])),
    True: dict(written=28, alive=18, rewritten=3, human=7, dropped=4, droppedWritten=5, aiLines=18, projectLines=37),
}
# 直し癖の手計算（gen_seizon.py の habits の節と対応）：(id, 回数, セッション数, ファイル数, 候補か, 型にならないか)
# 候補＝3回以上かつ2セッション以上。rename は3回でも1セッション＝参考。old.ts の丸ごと書き直し5行は block（癖ではない）
LOGS2 = HERE / "seizon" / "logs2"
PROJ2 = HERE / "seizon" / "proj" / "habits"
HAND_HABITS = [("debug", 3, 2, 2, True, False), ("rename", 3, 1, 1, False, False), ("any", 1, 1, 1, False, False), ("comment", 1, 1, 1, False, False),
               ("import", 1, 1, 1, False, False), ("quote", 1, 1, 1, False, False), ("string", 1, 1, 1, False, False),
               ("block", 5, 1, 1, False, True), ("delete", 1, 1, 1, False, True), ("other", 1, 1, 1, False, True)]
LOGS3 = HERE / "seizon" / "logs3"
PROJ3 = HERE / "seizon" / "proj" / "multi"
# Codex：x.ts を作って差分で two→five（書いた5・残った3・書き直し1・人が消した1・出力 50＋70・同じ response_id は1回・失敗した変更は数えない）
# Gemini：y.py を書いて return 'one'→'uno'（書いた5・残った4・書き直し1）。3か所に重ねて残った step は1回・切られた写しは full を使う・ほどけない値は数えず1件
# z.js：本文が " で始まる包まれていない値（"use strict";）もそのまま数える＝Antigravity は書いた 7・残った 6・出力 80・msgs 5。今は無い分 80×1/7＝11・1行あたり 80/6＝13
HAND_MULTI = dict(written=12, alive=9, rewritten=2, human=1, edits=5, sessions=2, uses=5, gmSkipped=1, root="/Users/t/dev/multi",
                  tools={"codex": {"written": 5, "alive": 3, "edits": 2, "sessions": 1}, "gemini": {"written": 7, "alive": 6, "edits": 3, "sessions": 1}},
                  rows=[("codex:cx-1", "codex", "x.ts を作って", 120, 2, 1, 5, 3, 40), ("gemini:11111111-2222-4333-8444-555555555555", "gemini", "y.py を作って", 80, 5, 1, 7, 6, 13)])
# 文脈とトークン（logs4・フォルダ無し）：Claude 6 応答（tm2 の2行は1応答）＋ Codex 2 応答＝8。15万超＝tm2・tm3・tm4・tm5・tr1・tr2＝6
# 再開（1時間以上あけた・サブエージェントは除く）＝t1 の 09:10→11:10・11:10→14:10、cx-t の 09:00→11:00＝3。一致＝tm4 だけ（前 220,003・読めた 1万＜2割・書いた 20万＞半分）
HAND_TOKENS = dict(n=8, over=6, bins=[2, 0, 0, 3, 3, 0, 0], resumes=3, matched=1, matchedMedianCw=200000,
                   by={"claude": {"n": 6, "over": 4, "resumes": 2, "matched": 1}, "codex": {"n": 2, "over": 2, "resumes": 1, "matched": 0}},
                   latest={"sid": "t1", "tool": "claude", "ts": "2026-09-20T11:10:00.000Z", "gapMin": 120, "prevCtx": 220003, "cr": 10000, "cw": 200000})
LOGS4 = HERE / "seizon" / "logs4"
# 書き直し（alpha）：a.ts の toArray の行・gone.ts の LEGACY の行・multi.ts の exponential の行・re.ts の RE2 の行＝4か所・4行・4ファイル
HAND_REWRITE = dict(total={"events": 4, "lines": 4, "files": 4}, files=["src/a.ts", "src/gone.ts", "src/multi.ts", "src/re.ts"],
                    first=("src/a.ts", "return db.notes.where({ userId }).toArray();", "a.ts に listNotes を足して、並びは updatedAt にして", True))
SINCE = 1788393600000   # 2026-09-03T00:00Z：s1（9/1）の行は数えない＝s2 の 6 行だけ・書き直しは 0
failures = 0

def check(name, got, want):
    global failures
    ok = got == want
    if not ok:
        failures += 1
    print(("OK  " if ok else "NG  ") + f"{name}: got={got!r} want={want!r}")
    return ok

def external_requests(reqs):
    return [r for r in reqs if not r.startswith(("file:", "data:", "blob:"))]

ROW_KEYS = ("file", "exists", "lines", "written", "alive", "rewritten", "human", "ai", "alias")

def compare(label, cur, exp):
    ok = True
    for k in ("written", "alive", "rewritten", "human", "dropped", "droppedWritten", "aiLines", "projectLines", "projectFiles", "otherProjectFiles", "edits", "sessions",
              "rootCandidates", "rootMatched", "rootFrom", "rootAmbiguous", "cwdTop", "uses", "logFiles", "logLines", "logBad", "root", "strict", "projectName", "period", "examples", "habits", "sessionStats", "since", "rewriteTotal", "rewriteFiles", "rewriteEvents"):
        ok &= check(f"{label} {k}", cur[k], exp[k])
    ok &= check(f"{label} files", [[r[k] for k in ROW_KEYS] for r in cur["files"]], [[r[k] for k in ROW_KEYS] for r in exp["files"]])
    ok &= check(f"{label} missingFiles", cur["missingFiles"], exp["missingFiles"])
    ok &= check(f"{label} top", cur["top"], exp["top"])
    return ok

def compare_hand(label, cur, strict):
    ok = True
    for k, v in HAND[strict].items():
        if k == "top":
            ok &= check(f"{label} hand top", [(t["file"], t["human"], t["written"], t["exists"]) for t in cur["top"]], v)
        elif k == "examples":
            ok &= check(f"{label} hand examples", {kk: (e["key"], e["file"]) if e else None for kk, e in cur["examples"].items()}, v)
        elif k == "sessionStats":
            S = cur["sessionStats"]
            ok &= check(f"{label} hand sessionStats totals", (S["outTotal"], S["outGone"], S["costly"], S["cheap"]), (v["outTotal"], v["outGone"], v["costly"], v["cheap"]))
            ok &= check(f"{label} hand sessionStats rows", [(r["sid"], r["first"], r["out"], r["outRepo"], r["msgs"], r["edits"], r["written"], r["alive"], r["rewritten"], r["human"], r["dropped"], r["perAlive"], r["start"], r["end"]) for r in S["rows"]], v["rows"])
        else:
            ok &= check(f"{label} hand {k}", cur[k], v)
    return ok

CURRENT = "JSON.parse(JSON.stringify(window.__seizon.current))"

# ---------- 文字列だけの小さな場面（root の決め方）＝ Codex レビュー 2026-10-20 の2件 ----------
def mk_write(path, content, ts, cwd, tid):
    use = {"type": "assistant", "cwd": cwd, "sessionId": "sx", "timestamp": ts, "uuid": "u-" + tid,
           "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": "Write", "input": {"file_path": path, "content": content}}]}}
    if cwd is None:
        del use["cwd"]
    res = {"type": "user", "cwd": cwd or "", "sessionId": "sx", "timestamp": ts, "uuid": "r-" + tid,
           "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": "File created successfully"}]},
           "toolUseResult": {"type": "create", "filePath": path, "content": content}}
    return json.dumps(use) + "\n" + json.dumps(res) + "\n"

IDX = "export const idx = 1;\nexport const idy = 2;\n"
def mk_edit(path, old, new, orig, ts, cwd, tid):
    use = {"type": "assistant", "cwd": cwd, "sessionId": "sx", "timestamp": ts, "uuid": "u-" + tid,
           "message": {"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": "Edit", "input": {"file_path": path, "old_string": old, "new_string": new}}]}}
    res = {"type": "user", "cwd": cwd, "sessionId": "sx", "timestamp": ts, "uuid": "r-" + tid,
           "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": "The file has been updated."}]},
           "toolUseResult": {"filePath": path, "oldString": old, "newString": new, "originalFile": orig, "structuredPatch": []}}
    return json.dumps(use) + "\n" + json.dumps(res) + "\n"
# 日時で区切った書き直し（Codex の指摘 PR #21）：9/1 に2行書き、9/5 に1行目を書き換え（区切りより前に入った行を消す）、9/6 に 9/5 の行を書き換え（区切りより後に入った行を消す）
RW_V1 = "export const one = 1;\nexport const two = 2;\n"
RW_V2 = "export const uno = 1;\nexport const two = 2;\n"
RW_LOGS = (mk_write("/rw/x.ts", RW_V1, "2026-09-01T00:00:00.000Z", "/rw", "w1")
           + mk_edit("/rw/x.ts", "export const one = 1;", "export const uno = 1;", RW_V1, "2026-09-05T00:00:00.000Z", "/rw", "w2")
           + mk_edit("/rw/x.ts", "export const uno = 1;", "export const ichi = 1;", RW_V2, "2026-09-06T00:00:00.000Z", "/rw", "w3"))
RW_PROJ = {"x.ts": "export const ichi = 1;\nexport const two = 2;\n"}
SCENES = {
    # 同数の候補（/repo と /repo/src）＝cwd と同じ /repo を選ぶ
    "tie-cwd": dict(logs=[mk_write("/repo/src/index.ts", IDX, "2026-09-01T00:00:00.000Z", "/repo", "t1")],
                    project={"index.ts": "export const root = 1;\n", "src/index.ts": IDX, "README.md": "# r\n"}, name="repo",
                    want=dict(root="/repo", rootFrom="files", rootAmbiguous=False, written=2, alive=2, human=0, dropped=0)),
    # 同数で cwd も無い＝浅い方を選び、決めきれなかった印を立てる
    "tie-nocwd": dict(logs=[mk_write("/repo/src/index.ts", IDX, "2026-09-01T00:00:00.000Z", None, "t2")],
                      project={"index.ts": "export const root = 1;\n", "src/index.ts": IDX, "README.md": "# r\n"}, name="repo",
                      want=dict(root="/repo", rootFrom="files", rootAmbiguous=True, written=2, alive=2, human=0)),
    # 触ったファイルが全部消えた＝フォルダ名が cwd の末尾と同じなら cwd を root にして「消えた」に数える
    "all-gone": dict(logs=[mk_write("/repo/gone.ts", IDX, "2026-09-01T00:00:00.000Z", "/repo", "t3")],
                     project={"README.md": "# r\n"}, name="repo",
                     want=dict(root="/repo", rootFrom="cwd", rootAmbiguous=False, written=2, alive=0, human=2, dropped=2, droppedWritten=2)),
    # 全部消えていて、フォルダ名も合わない＝root 無し（読めませんでした）
    "all-gone-wrong-folder": dict(logs=[mk_write("/repo/gone.ts", IDX, "2026-09-01T00:00:00.000Z", "/repo", "t4")],
                                  project={"README.md": "# r\n"}, name="other",
                                  want=dict(root="", rootFrom="", rootAmbiguous=False, written=0, alive=0, human=0)),
}

with sync_playwright() as p:
    b = p.chromium.launch()
    for label, vp, scheme in [("desktop-light", {"width": 1280, "height": 1000}, "light"), ("mobile-dark", {"width": 390, "height": 844}, "dark")]:
        ctx = b.new_context(viewport=vp, color_scheme=scheme, timezone_id="Asia/Tokyo", locale="ja-JP", device_scale_factor=2 if "mobile" in label else 1, bypass_csp=True)
        page = ctx.new_page()
        errs, reqs = [], []
        page.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        page.on("request", lambda r: reqs.append(r.url))
        page.goto(URL)
        page.wait_for_function("document.getElementById('cardImg').src.startsWith('data:image/png')")
        page.screenshot(path=str(SHOTS / f"seizon-sample-{label}.png"), full_page=True)
        check(f"{label} default tab tokens", (page.evaluate("window.__seizon.tab"), page.text_content("#statusPill")), ("tokens", "見本"))
        page.click(".tab[data-tab=rework]"); page.wait_for_timeout(200)
        page.screenshot(path=str(SHOTS / f"seizon-sample-rework-{label}.png"), full_page=True)
        check(f"{label} rework sample rewrites shown", page.evaluate("document.querySelectorAll('#details .rwev').length > 0"), True)
        check(f"{label} rework overflow", page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"), False)
        page.click(".tab[data-tab=tokens]"); page.wait_for_timeout(200)
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        check(f"{label} horizontal overflow", overflow, False)
        if label == "desktop-light":
            src = page.get_attribute("#cardImg", "src")
            (SHOTS / "seizon-card-sample.png").write_bytes(base64.b64decode(src.split(",", 1)[1]))
            # 0) 文脈とトークン：ログだけで数字が出る＝手計算 HAND_TOKENS ＝ Python ＝ Chromium
            page.set_input_files("#logInput", str(LOGS4))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのログ'", timeout=20000)
            curT = page.evaluate("JSON.parse(JSON.stringify(window.__seizon.currentT))")
            expT = ref_seizon.run_tokens(sorted(LOGS4.rglob("*.jsonl")))
            ok = True
            for k in ("n", "over", "bins", "by", "period", "resumes", "matched", "matchedMedianCw", "latest", "weighted"):
                ok &= check(f"tokens js=py {k}", curT[k], expT[k])
            for k, v in HAND_TOKENS.items():
                ok &= check(f"tokens hand {k}", [b["n"] for b in curT["bins"]] if k == "bins" else curT[k], v)
            ok &= check("tokens weighted sums to 1", round(sum(curT["weighted"].values()), 6), 1.0)
            tok_txt = page.input_value("#shareText")
            ok &= check("tokens share text", ("75%" in tok_txt, "#AI開発ログマップ" in tok_txt, "t1" in tok_txt), (True, True, False))
            ok &= check("tokens details latest", page.evaluate("(t => t.includes('2時間') && t.includes('20:10'))(document.querySelector('#details .latest').textContent)"), True)
            page.screenshot(path=str(SHOTS / "seizon-tokens-mine.png"), full_page=True)
            src = page.get_attribute("#cardImg", "src")
            (SHOTS / "seizon-card-tokens.png").write_bytes(base64.b64decode(src.split(",", 1)[1]))
            print("tokens share text:\n" + tok_txt)
            page.click("#logClear")
            ok &= check("tokens cleared to sample", page.text_content("#statusPill"), "見本")
            # 1) ログだけ → 文脈とトークンは出る・手直しのタブは「あと1つ」
            page.set_input_files("#logInput", str(LOGS))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのログ'", timeout=20000)
            page.click(".tab[data-tab=rework]")
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あと1つ'", timeout=20000)
            print("after logs:", page.locator("#logLoaded").text_content())
            # 2) フォルダ → 突き合わせ
            page.set_input_files("#projInput", str(PROJ))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのコード'", timeout=20000)
            print("after project:", page.locator("#projLoaded").text_content(), "|", page.locator("#statusText").text_content())
            cur = page.evaluate(CURRENT)
            ok &= compare("normal", cur, expect[False]) & compare_hand("normal", cur, False)
            ok &= check("rewrite hand total", cur["rewriteTotal"], HAND_REWRITE["total"])
            ok &= check("rewrite hand files", [f["file"] for f in cur["rewriteFiles"]], HAND_REWRITE["files"])
            e0 = cur["rewriteEvents"][0]
            ok &= check("rewrite hand first", (e0["file"], e0["gone"][0], e0["prompt"]["text"], e0["prompt"]["first"]), HAND_REWRITE["first"])
            ok &= check("rewrite prompt on screen", page.evaluate("document.querySelector('#details .rwev') !== null && document.getElementById('details').textContent.includes('並びは updatedAt にして')"), True)
            ok &= check("rewrite prompt not in share", "updatedAt" in page.input_value("#shareText"), False)
            page.screenshot(path=str(SHOTS / "seizon-mine-desktop-light.png"), full_page=True)
            src = page.get_attribute("#cardImg", "src")
            (SHOTS / "seizon-card-mine.png").write_bytes(base64.b64decode(src.split(",", 1)[1]))
            print("share text:\n" + page.input_value("#shareText"))
            # 3) 厳密モード
            page.check("#optStrict")
            page.wait_for_function("window.__seizon.current.strict === true", timeout=20000)
            cur2 = page.evaluate(CURRENT)
            ok &= compare("strict", cur2, expect[True]) & compare_hand("strict", cur2, True)
            page.uncheck("#optStrict")
            page.wait_for_function("window.__seizon.current.strict === false", timeout=20000)
            # 4) 名前を隠す・典型例を載せる（描画が通ること）
            page.check("#optHideFiles"); page.check("#optHideProject"); page.check("#optExamples")
            page.wait_for_timeout(300)
            src = page.get_attribute("#cardImg", "src")
            (SHOTS / "seizon-card-hidden.png").write_bytes(base64.b64decode(src.split(",", 1)[1]))
            hidden_ok = page.evaluate("!document.getElementById('details').textContent.includes('src/a.ts')")
            ok &= check("hidden file names in details", hidden_ok, True)
            # 5) 文字列から同じ計算（analyzeTexts）＝別経路でも同じ値
            logs_js = [{"path": str(f), "text": f.read_text(encoding="utf-8")} for f in log_files]
            proj_js = [{"rel": f.relative_to(PROJ).as_posix(), "text": f.read_bytes().decode("utf-8", errors="replace")} for f in sorted(PROJ.rglob("*")) if f.is_file()]
            cur3 = page.evaluate("([l, p]) => JSON.parse(JSON.stringify(window.__seizon.analyzeTexts(l, p, 'alpha', false)))", [logs_js, proj_js])
            ok &= check("analyzeTexts written/alive/human", (cur3["written"], cur3["alive"], cur3["human"], cur3["aiLines"], cur3["projectFiles"]),
                        (expect[False]["written"], expect[False]["alive"], expect[False]["human"], expect[False]["aiLines"], expect[False]["projectFiles"]))
            cur_s = page.evaluate("([l, p, t]) => JSON.parse(JSON.stringify(window.__seizon.analyzeTexts(l, p, 'alpha', false, t)))", [logs_js, proj_js, SINCE])
            exp_s = ref_seizon.run(log_files, PROJ, strict=False, since=SINCE)
            for k in ("written", "alive", "rewritten", "human", "since", "rewriteTotal", "files"):
                ok &= check(f"since js=py {k}", cur_s[k], exp_s[k])
            ok &= check("since hand", (cur_s["written"], cur_s["rewriteTotal"]["events"], cur_s["since"]), (6, 0, "2026-09-03T00:00:00.000Z"))
            page.fill("#optSince", "2026-09-03T09:00")   # 東京の 9/3 9:00 ＝ SINCE
            page.dispatch_event("#optSince", "change")
            page.wait_for_function("window.__seizon.current.since === '2026-09-03T00:00:00.000Z'", timeout=20000)
            ok &= check("since ui written", page.evaluate("window.__seizon.current.written"), 6)
            ok &= check("since status note", "以降に入った行だけ" in page.text_content("#statusText"), True)
            page.click("#clearSince")
            page.wait_for_function("window.__seizon.current.since === null", timeout=20000)
            ok &= check("since cleared written", page.evaluate("window.__seizon.current.written"), expect[False]["written"])
            # 6) 文字列だけの小さな場面（root の決め方）＝JS・Python・手の3つが一致
            for name, sc in SCENES.items():
                js = page.evaluate("([l, p, n]) => JSON.parse(JSON.stringify(window.__seizon.analyzeTexts(l, p, n, false)))",
                                   [[{"path": "x.jsonl", "text": t} for t in sc["logs"]], [{"rel": k, "text": v} for k, v in sc["project"].items()], sc["name"]])
                py = ref_seizon.run_texts(sc["logs"], sc["project"], sc["name"])
                for k, v in sc["want"].items():
                    ok &= check(f"scene {name} {k}", (js[k], py[k]), (v, v))
            for since, want in ((None, (2, 2)), (SINCE, (1, 1))):
                js = page.evaluate("([l, p, t]) => JSON.parse(JSON.stringify(window.__seizon.analyzeTexts(l, p, 'rw', false, t)))", [[{"path": "x.jsonl", "text": RW_LOGS}], [{"rel": k, "text": v} for k, v in RW_PROJ.items()], since])
                py = ref_seizon.run_texts([RW_LOGS], RW_PROJ, "rw", since=since)
                ok &= check(f"rewrite since={since} js", (js["rewriteTotal"]["events"], js["rewriteTotal"]["lines"]), want)
                ok &= check(f"rewrite since={since} py=js", (py["rewriteTotal"], py["rewriteEvents"], py["written"]), (js["rewriteTotal"], js["rewriteEvents"], js["written"]))
            # 7) ログのフォルダを右（プロジェクト）に入れた時＝「ログのフォルダのようです」で止まり、前の結果は残る（2026-10-20 に本人が踏んだ）
            page.set_input_files("#projInput", str(LOGS / "projects"))
            page.wait_for_function("document.getElementById('statusPill').textContent === '読めませんでした'", timeout=20000)
            msg = page.locator("#statusText").text_content()
            print("logs-as-project:", msg)
            ok &= check("logs-as-project guard", "ログのフォルダのようです" in msg, True)
            ok &= check("logs-as-project keeps result", page.evaluate("window.__seizon.current.written"), expect[False]["written"])
            # 8) 直し癖：別のログ（logs2）とプロジェクト（habits）＝手計算 HAND_HABITS ＝ Python ＝ Chromium
            page.set_input_files("#logInput", str(LOGS2))
            page.wait_for_function("document.getElementById('logLoaded').textContent.includes('5ファイル')", timeout=20000)
            page.set_input_files("#projInput", str(PROJ2))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのコード' && window.__seizon.current.projectName === 'habits'", timeout=20000)
            cur_h = page.evaluate(CURRENT)
            exp_h = ref_seizon.run(sorted(LOGS2.rglob("*.jsonl")), PROJ2, strict=False)
            ok &= check("habits written/alive/human", (cur_h["written"], cur_h["alive"], cur_h["human"], cur_h["dropped"]), (27, 9, 18, 0))
            ok &= check("habits js=py", cur_h["habits"], exp_h["habits"])
            ok &= check("habits hand", [(it["id"], it["count"], it["sessions"], it["files"], it["candidate"], it["generic"]) for it in cur_h["habits"]["items"]], HAND_HABITS)
            ok &= check("habits lines/matched", (cur_h["habits"]["lines"], cur_h["habits"]["matched"]), (18, 8))
            # 頼み方（habits）：h4 と h5 は --resume の関係（同じ uuid・別の sessionId）＝1つの会話にまとめる。出力 100×4 セッション＋h5 の新しい1通＝500
            #   今は無い分＝h1 100×7/10=70・h2 100×4/7=57・h3 100・h4+h5 200×2/5=80 → 307。20行以上書いた会話が無いので costly/cheap は空
            Sh = cur_h["sessionStats"]
            ok &= check("habits sessionStats totals", (Sh["outTotal"], Sh["outGone"], Sh["costly"], Sh["cheap"], cur_h["sessions"]), (500, 307, [], [], 4))
            ok &= check("habits sessionStats rows", [(r["sid"], r["first"], r["out"], r["outRepo"], r["msgs"], r["members"], r["edits"], r["written"], r["alive"], r["perAlive"]) for r in Sh["rows"]],
                        [("h4", "tool.py を作って", 200, 200, 2, 2, 2, 5, 3, 67), ("h1", "app.ts を書いて", 100, 100, 1, 1, 1, 10, 3, 33), ("h2", "util.ts を書いて", 100, 100, 1, 1, 1, 7, 3, 33), ("h3", "キャッシュをとりあえず作って", 100, 100, 1, 1, 1, 5, 0, None)])
            # 文脈とトークンは、ログを読む順に左右されない（h5 が h4 を --resume で写す＝どちらを先に読むかで応答の sid が変わる。実データで再開の数が 2 ずれた）
            L2 = [{"path": str(f), "text": f.read_text(encoding="utf-8")} for f in sorted(LOGS2.rglob("*.jsonl"))]
            t_fwd = page.evaluate("l => JSON.parse(JSON.stringify(window.__seizon.tokenTexts(l)))", L2)
            t_rev = page.evaluate("l => JSON.parse(JSON.stringify(window.__seizon.tokenTexts(l)))", L2[::-1])
            ok &= check("tokens order independent", {k: t_rev[k] for k in ("n", "resumes", "matched", "by", "latest")}, {k: t_fwd[k] for k in ("n", "resumes", "matched", "by", "latest")})
            ok &= check("tokens py reversed", {k: ref_seizon.run_tokens(sorted(LOGS2.rglob("*.jsonl"))[::-1])[k] for k in ("n", "resumes", "matched", "by")}, {k: t_fwd[k] for k in ("n", "resumes", "matched", "by")})
            # 写しの場面：a が 9:00・9:05 に応答、--resume した b が同じ2行（同じ uuid・message.id）を写して 11:00 に応答＝つないだ会話で 115 分あいた再開 1 回。
            # 直す前は a を先に読むと 0 回・b を先に読むと 1 回だった
            def tkl(sid, uid, mid, ts, cr, cw):
                return json.dumps({"type": "assistant", "sessionId": sid, "uuid": uid, "timestamp": ts, "isSidechain": False,
                                   "message": {"id": mid, "role": "assistant", "content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 3, "output_tokens": 10, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}}})
            fa = "\n".join([tkl("ra", "u1", "m1", "2026-09-22T00:00:00.000Z", 0, 30000), tkl("ra", "u2", "m2", "2026-09-22T00:05:00.000Z", 30000, 1000)]) + "\n"
            fb = "\n".join([tkl("rb", "u1", "m1", "2026-09-22T00:00:00.000Z", 0, 30000), tkl("rb", "u2", "m2", "2026-09-22T00:05:00.000Z", 30000, 1000), tkl("rb", "u3", "m3", "2026-09-22T02:00:00.000Z", 0, 31000)]) + "\n"
            for nm, order in (("a→b", [fa, fb]), ("b→a", [fb, fa])):
                tj = page.evaluate("l => JSON.parse(JSON.stringify(window.__seizon.tokenTexts(l)))", [{"path": f"{i}.jsonl", "text": t} for i, t in enumerate(order)])
                ok &= check(f"resume copy {nm}", (tj["n"], tj["resumes"], tj["matched"], tj["latest"]["gapMin"] if tj["latest"] else None), (3, 1, 1, 115))
            ok &= check("habits resume shown", page.evaluate("document.getElementById('details').textContent.includes('再開 1 回を含む')"), True)
            ok &= check("habits rule text", [it["rule"] for it in cur_h["habits"]["items"] if it["candidate"]], ["デバッグ用の出力（console.log など）は残さない。"])
            ok &= check("habits rename dir", [it["dir"] for it in cur_h["habits"]["items"] if it["id"] == "rename"], ["total → sum"])
            ok &= check("habits cards rendered", page.evaluate("document.querySelectorAll('#details .habit').length"), 1)
            ok &= check("habits guard shown", page.evaluate("document.querySelector('#details .habit').textContent.includes('機械で防ぐ')"), True)
            page.select_option("#details select[data-mark=debug]", index=1)
            mark_v = page.evaluate("document.querySelector('#details select[data-mark=debug]').value")
            ok &= check("habits mark saved", page.evaluate("window.__seizon.snapshotOf(window.__seizon.current).marks"), {"debug": mark_v})
            # import の型の境界（Codex の指摘 #15・#16）：引用符の無い import・別名つきの一覧
            PAIRS = [("import foo as f, bar", "import foobar", "import"), ("import foo as f, bar", "import foo, bar", "other"), ("import os", "import os, sys", "import"),
                     ("from oldpkg.utils import foo", "from newpkg.utils import foo", "import"), ("from pkg import a", "from pkg import a, b", "other"),
                     ('import { a } from "./x";', 'import { a, b } from "./x";', "other"), ('import { a } from "./x";', "import { a } from './x';", "quote"), ('import { a } from "./x";', 'import { a } from "./x.js";', "import")]
            js_ids = page.evaluate("ps => ps.map(([b, a]) => window.__seizon.classifyPair(b, a, 'py').id)", [[b, a] for b, a, _ in PAIRS])
            py_ids = [ref_seizon.classify_pair(b, a, "py")[0] for b, a, _ in PAIRS]
            ok &= check("classifyPair import boundary js", js_ids, [w for _, _, w in PAIRS])
            ok &= check("classifyPair import boundary py", py_ids, [w for _, _, w in PAIRS])
            ok &= check("habits weak listed", page.evaluate("document.getElementById('details').textContent.includes('回数が足りない型')"), True)
            # 9) Codex と Gemini（logs3・multi）：Codex を入れてから Gemini を入れる＝別の AI なので足す。手計算 HAND_MULTI ＝ Python ＝ Chromium
            page.click("#logClear")   # 前の Claude Code のログ（habits）を外してから（別の AI のログは足されるので）
            ok &= check("log clear", page.evaluate("document.getElementById('logLoaded').hidden && window.__seizon.inputs.acc === null"), True)
            page.set_input_files("#logInput", str(LOGS3 / "codex"))
            page.wait_for_function("document.getElementById('logLoaded').textContent.includes('Codex 2件')", timeout=20000)
            page.set_input_files("#logInput", str(LOGS3 / "gemini"))
            page.wait_for_function("document.getElementById('logLoaded').textContent.includes('Antigravity 3件')", timeout=20000)
            ok &= check("multi loaded both", "Codex 2件" in page.text_content("#logLoaded"), True)
            page.set_input_files("#projInput", str(PROJ3))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのコード' && window.__seizon.current.projectName === 'multi'", timeout=20000)
            cur_m = page.evaluate(CURRENT)
            exp_m = ref_seizon.run(sorted(LOGS3.rglob("*.jsonl")), PROJ3, strict=False)
            for k in ("written", "alive", "rewritten", "human", "dropped", "edits", "sessions", "root", "uses", "gmSkipped", "tools", "period", "sessionStats", "files"):
                ok &= check(f"multi js=py {k}", cur_m[k], exp_m[k])
            for k, v in HAND_MULTI.items():
                ok &= check(f"multi hand {k}", cur_m[k] if k != "rows" else [(r["sid"], r["tool"], r["first"], r["out"], r["msgs"], r["bash"], r["written"], r["alive"], r["perAlive"]) for r in cur_m["sessionStats"]["rows"]], v)
            ok &= check("multi outGone", (cur_m["sessionStats"]["outTotal"], cur_m["sessionStats"]["outGone"]), (200, 59))
            # 前回と比べる：前回が Claude の結果なら「AI」と書き、違いを注意する（Codex の指摘 PR #20）
            snap_m = page.evaluate("window.__seizon.snapshotOf(window.__seizon.current)")
            ok &= check("multi snapshot ai", (snap_m["ai"], snap_m["ais"]), ("AI", ["codex", "gemini"]))
            prev_m = dict(snap_m, ai="Claude", savedAt="2026-09-01"); prev_m.pop("ais")
            page.evaluate("s => window.__seizon.loadPrev(s)", prev_m)
            ok &= check("multi compare warns other AI", page.evaluate("document.getElementById('details').textContent.includes('前回は Claude の結果、今回は Codex＋Antigravity の結果です')"), True)
            page.click("#clearPrev")
            # どちらも複数の AI でも、組が違えば注意する（Codex の指摘 PR #20：Claude＋Codex と Codex＋Antigravity は同じ「AI」ではない）
            page.evaluate("s => window.__seizon.loadPrev(s)", dict(snap_m, ais=["claude", "codex"], savedAt="2026-09-01"))
            ok &= check("multi compare warns other AI set", page.evaluate("document.getElementById('details').textContent.includes('前回は Claude＋Codex の結果、今回は Codex＋Antigravity の結果です')"), True)
            page.click("#clearPrev")
            page.evaluate("s => window.__seizon.loadPrev(s)", dict(snap_m, savedAt="2026-09-01"))
            ok &= check("multi compare same AI set no warn", page.evaluate("document.getElementById('details').textContent.includes('書いた AI が違うので')"), False)
            page.click("#clearPrev")
            ok &= check("multi card title", page.evaluate("document.getElementById('details').textContent.includes('Antigravity が書いた行')"), True)
            ok &= check("multi label AI", "AI が書いた" in page.input_value("#shareText"), True)
            # 同じ AI のログを入れ直すと置き換える（Codex だけになる）
            page.set_input_files("#logInput", str(LOGS3 / "codex"))
            page.wait_for_function("!document.getElementById('logLoaded').textContent.includes('Antigravity') && window.__seizon.current.written === 5", timeout=20000)
            ok &= check("multi replace same tool", (page.evaluate("window.__seizon.current.written"), "Codex が書いた" in page.input_value("#shareText")), (5, True))
            prev_c = dict(page.evaluate("window.__seizon.snapshotOf(window.__seizon.current)"), savedAt="2026-09-01")
            page.evaluate("s => window.__seizon.loadPrev(s)", prev_c)
            ok &= check("compare same AI keeps name", page.evaluate("[...document.querySelectorAll('#details .rows li')].some(li => li.textContent.includes('Codex が書いた行'))"), True)
            page.click("#clearPrev")
            # 会話の節：出る・指示の冒頭が見える・隠すと消える・共有文に1行
            ok &= check("sessions section present", page.evaluate("[...document.querySelectorAll('#details .sec h2')].some(h => h.textContent === '出力が大きかった会話と、残った1行あたりの出力トークン')"), True)
            ok &= check("sessions prompt shown", page.evaluate("document.getElementById('details').textContent.includes('a.ts に listNotes を足して')"), False)  # habits プロジェクトには user text が無い
            page.set_input_files("#logInput", str(LOGS)); page.set_input_files("#projInput", str(PROJ))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのコード' && window.__seizon.current.projectName === 'alpha'", timeout=20000)
            ok &= check("sessions prompt shown (alpha)", page.evaluate("document.getElementById('details').textContent.includes('a.ts に listNotes を足して')"), True)
            ok &= check("sessions pasted tag stripped", page.evaluate("document.getElementById('details').textContent.includes('pasted_content')"), False)
            ok &= check("share text has token line", "今は無いコードに使った出力トークン：18%（573／3,200）" in page.input_value("#shareText"), True)
            page.check("#optHidePrompts"); page.wait_for_timeout(200)
            ok &= check("sessions prompt hidden", page.evaluate("document.getElementById('details').textContent.includes('a.ts に listNotes を足して')"), False)
            page.uncheck("#optHidePrompts"); page.wait_for_timeout(200)
            page.set_input_files("#logInput", str(LOGS2)); page.set_input_files("#projInput", str(PROJ2))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのコード' && window.__seizon.current.projectName === 'habits'", timeout=20000)
            page.screenshot(path=str(SHOTS / "seizon-habits.png"), full_page=True)
            # 9) 結果の保存（JSON）と前回との比較：数だけ・行の中身は入らない／減った型が緑
            snap = page.evaluate("window.__seizon.snapshotOf(window.__seizon.current)")
            ok &= check("snapshot keys", (snap["tool"], snap["projectName"], snap["written"], len(snap["habits"]), "examples" in json.dumps(snap), "console.log" in json.dumps(snap), "outTotal" in snap, "first" in json.dumps(snap)), ("cc-seizon", "habits", 27, 10, False, False, True, False))
            prev = json.loads(json.dumps(snap)); prev["savedAt"] = "2026-09-01"
            for h in prev["habits"]:
                if h["id"] == "debug": h["count"] = 5
            ok &= check("loadPrev", page.evaluate("s => window.__seizon.loadPrev(s)", prev), True)
            ok &= check("compare rendered", page.evaluate("[...document.querySelectorAll('#details .sec h2')].some(h => h.textContent === '前回と比べる')"), True)
            # 前回を読んだら、比べる節（3つ目）が画面の上に来る（Codex の指摘 PR #17：2つ目の節に飛んでいた）
            ok &= check("compare scrolled into view", page.evaluate("Math.abs(document.querySelector('#details .sec[data-kicker=\"前回\"]').getBoundingClientRect().top) < 2"), True)
            ok &= check("compare delta", page.evaluate("[...document.querySelectorAll('#details .rows li')].some(li => li.textContent.includes('デバッグ出力の削除') && li.textContent.includes('5 → 3') && li.querySelector('.delta.good') !== null)"), True)
            ok &= check("loadPrev rejects foreign json", page.evaluate("window.__seizon.loadPrev({foo: 1})"), False)
            page.click("#clearPrev")
            ok &= check("compare cleared", page.evaluate("[...document.querySelectorAll('#details .sec h2')].some(h => h.textContent === '前回と比べる')"), False)
            # 10) 見本に戻す
            page.click("#resetBtn")
            page.wait_for_function("document.getElementById('statusPill').textContent === '見本'")
            print("ALL MATCH" if ok else "MISMATCH")
        print(f"[{label}] errors: {errs}")
        print(f"[{label}] requests: {[r for r in reqs if not r.startswith('data:')]}")
        check(f"{label} browser errors/warnings", errs, [])
        check(f"{label} external requests", external_requests(reqs), [])
        ctx.close()
    # CSP を効かせたまま：エラーなし・画像が出る・ファイルが読める・外部通信なし
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, timezone_id="Asia/Tokyo", locale="ja-JP")
    page = ctx.new_page(); errs = []; reqs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: reqs.append(r.url))
    page.goto(URL)
    page.locator("#statusPill", has_text="見本").wait_for()
    page.wait_for_function("""() => {
        const img = document.getElementById('cardImg');
        return img.src.startsWith('data:image/png') && img.complete && img.naturalWidth > 0;
    }""")
    page.set_input_files("#projInput", str(PROJ))
    page.locator("#statusPill", has_text="あと1つ").wait_for(timeout=20000)
    page.set_input_files("#logInput", str(LOGS))
    page.locator("#statusPill", has_text="あなたのコード").wait_for(timeout=20000)
    cur = page.evaluate(CURRENT)
    check("csp written/alive", (cur["written"], cur["alive"]), (expect[False]["written"], expect[False]["alive"]))
    print("[csp] status:", page.locator("#statusText").text_content())
    print("[csp] errors:", errs)
    print("[csp] non-data requests:", [r for r in reqs if not r.startswith("data:")])
    check("csp browser errors", errs, [])
    check("csp external requests", external_requests(reqs), [])
    ctx.close()
    b.close()

print(f"CHECK FAILURES: {failures}")
sys.exit(1 if failures else 0)
