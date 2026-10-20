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
    False: dict(written=26, alive=17, rewritten=3, human=6, dropped=4, droppedWritten=5, aiLines=17, projectLines=35, projectFiles=11, edits=11, sessions=2,
                otherProjectFiles=2, rootCandidates=2, rootMatched=8, uses=18, logFiles=4, logBad=1, root="/Users/t/dev/alpha",
                period={"start": "2026-09-01", "end": "2026-09-05", "days": 5},
                top=[("src/a.ts", 1, 6, True), ("src/c.ts", 1, 3, True)],
                examples={"alive": ("return db.notes.where({ userId }).sortBy('updatedAt');", "src/a.ts"),
                          "human": ("return list.reduce((x, y) => x + y, 0);", "src/c.ts")},
                # 頼み方：s1＝12通×100＝1,200・21行書いて12行残存（消えた9行）→ 今は無い分 1,200×9/21=514・残った1行あたり 100
                #         s2＝6通×300＝1,800・alpha に5行＋別の場所に1行（decoy）＝按分 5/6 → 1,500・全部残存 → 0・1行あたり 300
                #         再開で写った s1 の2通（s2.jsonl の先頭）は uuid で重複を除く＝s1 は 12 通のまま。20行以上書いたのは s1 だけ＝高くて消えた・安くて残ったは無し（残存 57%）
                sessionStats=dict(outTotal=2700, outGone=514, costly=["s1"], cheap=[],
                                  rows=[("s2", "引き継ぎ：win.ts・sec.ts・d.ts を足す。範囲外は触らない", 1800, 1500, 6, 3, 5, 5, 0, 0, 0, 300, "2026-09-03", "2026-09-05"),   # s2 の写しは sessionId が s1 のまま＝別の会話のまま（本物の再開は habits の h5 で試す）
                                        ("s1", "a.ts に listNotes を足して、並びは updatedAt にして", 1200, 1200, 12, 8, 21, 12, 3, 2, 4, 100, "2026-09-01", "2026-09-01")])),
    True: dict(written=26, alive=16, rewritten=3, human=7, dropped=4, droppedWritten=5, aiLines=16, projectLines=35),
}
# 直し癖の手計算（gen_seizon.py の habits の節と対応）：(id, 回数, セッション数, ファイル数, 候補か, 型にならないか)
# 候補＝3回以上かつ2セッション以上。rename は3回でも1セッション＝参考。old.ts の丸ごと書き直し5行は block（癖ではない）
LOGS2 = HERE / "seizon" / "logs2"
PROJ2 = HERE / "seizon" / "proj" / "habits"
HAND_HABITS = [("debug", 3, 2, 2, True, False), ("rename", 3, 1, 1, False, False), ("any", 1, 1, 1, False, False), ("comment", 1, 1, 1, False, False),
               ("import", 1, 1, 1, False, False), ("quote", 1, 1, 1, False, False), ("string", 1, 1, 1, False, False),
               ("block", 5, 1, 1, False, True), ("delete", 1, 1, 1, False, True), ("other", 1, 1, 1, False, True)]
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
              "rootCandidates", "rootMatched", "rootFrom", "rootAmbiguous", "cwdTop", "uses", "logFiles", "logLines", "logBad", "root", "strict", "projectName", "period", "examples", "habits", "sessionStats"):
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
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        check(f"{label} horizontal overflow", overflow, False)
        if label == "desktop-light":
            src = page.get_attribute("#cardImg", "src")
            (SHOTS / "seizon-card-sample.png").write_bytes(base64.b64decode(src.split(",", 1)[1]))
            # 1) ログだけ → 「あと1つ」
            page.set_input_files("#logInput", str(LOGS))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あと1つ'", timeout=20000)
            print("after logs:", page.locator("#logLoaded").text_content())
            # 2) フォルダ → 突き合わせ
            page.set_input_files("#projInput", str(PROJ))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのコード'", timeout=20000)
            print("after project:", page.locator("#projLoaded").text_content(), "|", page.locator("#statusText").text_content())
            cur = page.evaluate(CURRENT)
            ok = compare("normal", cur, expect[False]) & compare_hand("normal", cur, False)
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
            # 6) 文字列だけの小さな場面（root の決め方）＝JS・Python・手の3つが一致
            for name, sc in SCENES.items():
                js = page.evaluate("([l, p, n]) => JSON.parse(JSON.stringify(window.__seizon.analyzeTexts(l, p, n, false)))",
                                   [[{"path": "x.jsonl", "text": t} for t in sc["logs"]], [{"rel": k, "text": v} for k, v in sc["project"].items()], sc["name"]])
                py = ref_seizon.run_texts(sc["logs"], sc["project"], sc["name"])
                for k, v in sc["want"].items():
                    ok &= check(f"scene {name} {k}", (js[k], py[k]), (v, v))
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
            ok &= check("habits resume shown", page.evaluate("document.getElementById('details').textContent.includes('再開 1 回を含む')"), True)
            ok &= check("habits rule text", [it["rule"] for it in cur_h["habits"]["items"] if it["candidate"]], ["デバッグ用の出力（console.log など）は残さない。"])
            ok &= check("habits rename dir", [it["dir"] for it in cur_h["habits"]["items"] if it["id"] == "rename"], ["total → sum"])
            ok &= check("habits cards rendered", page.evaluate("document.querySelectorAll('#details .habit').length"), 1)
            # import の型の境界（Codex の指摘 #15・#16）：引用符の無い import・別名つきの一覧
            PAIRS = [("import foo as f, bar", "import foobar", "import"), ("import foo as f, bar", "import foo, bar", "other"), ("import os", "import os, sys", "import"),
                     ("from oldpkg.utils import foo", "from newpkg.utils import foo", "import"), ("from pkg import a", "from pkg import a, b", "other"),
                     ('import { a } from "./x";', 'import { a, b } from "./x";', "other"), ('import { a } from "./x";', "import { a } from './x';", "quote"), ('import { a } from "./x";', 'import { a } from "./x.js";', "import")]
            js_ids = page.evaluate("ps => ps.map(([b, a]) => window.__seizon.classifyPair(b, a, 'py').id)", [[b, a] for b, a, _ in PAIRS])
            py_ids = [ref_seizon.classify_pair(b, a, "py")[0] for b, a, _ in PAIRS]
            ok &= check("classifyPair import boundary js", js_ids, [w for _, _, w in PAIRS])
            ok &= check("classifyPair import boundary py", py_ids, [w for _, _, w in PAIRS])
            ok &= check("habits weak listed", page.evaluate("document.getElementById('details').textContent.includes('回数が足りない型')"), True)
            # 頼み方の節：最初に出る・指示の冒頭が見える・隠すと消える・共有文に1行
            ok &= check("sessions section first", page.evaluate("document.querySelector('#details .sec h2').textContent"), "頼み方と、残った1行あたりの出力トークン")
            ok &= check("sessions prompt shown", page.evaluate("document.getElementById('details').textContent.includes('a.ts に listNotes を足して')"), False)  # habits プロジェクトには user text が無い
            page.set_input_files("#logInput", str(LOGS)); page.set_input_files("#projInput", str(PROJ))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのコード' && window.__seizon.current.projectName === 'alpha'", timeout=20000)
            ok &= check("sessions prompt shown (alpha)", page.evaluate("document.getElementById('details').textContent.includes('a.ts に listNotes を足して')"), True)
            ok &= check("sessions pasted tag stripped", page.evaluate("document.getElementById('details').textContent.includes('pasted_content')"), False)
            ok &= check("share text has token line", "今は無いコードに使った出力トークン：19%（514／2,700）" in page.input_value("#shareText"), True)
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
