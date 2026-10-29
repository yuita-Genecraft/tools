#!/usr/bin/env python3
"""通知表を Chromium で開いて、見本表示・ファイル投入・集計値の突き合わせ・スクショまでを通す。"""
import base64, json, pathlib, subprocess, sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
APP = HERE.parent / "cc-tsuchihyo"
SHOTS = HERE / "shots"
SHOTS.mkdir(exist_ok=True)
subprocess.run([sys.executable, str(HERE.parent / "build_standalone.py"), str(APP / "app.html"), str(APP / "dist" / "index.html")], check=True)
if not (HERE / "logs").exists():
    subprocess.run([sys.executable, str(HERE / "gen.py")], check=True)
sys.path.insert(0, str(HERE))
import ref  # noqa

URL = (APP / "dist" / "index.html").as_uri()
proj = HERE / "logs" / "projects"
files = sorted(str(p) for p in proj.rglob("*.jsonl"))
expect = ref.run([pathlib.Path(f) for f in files])
extra = [str(p) for p in sys.argv[1:]]
failures = 0

def check(name, got, want, tol=1e-9):
    global failures
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    if not ok:
        failures += 1
    print(("OK  " if ok else "NG  ") + f"{name}: got={got} want={want}")
    return ok

# canvas の fillText の引数（文字・位置・書体・色・canvas の大きさ）を記録する：画像の中の文字を検査するため
FILLTEXT_SPY = """(() => { window.__fillTextCalls = []; const f = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function (s, x, y) { window.__fillTextCalls.push({ s: String(s), x, y, font: this.font, color: this.fillStyle, align: this.textAlign, w: this.canvas.width, h: this.canvas.height }); return f.apply(this, arguments); }; })();"""

def external_requests(reqs):
    # Local HTML, generated images, and in-memory blobs are expected.
    return [r for r in reqs if not r.startswith(("file:", "data:", "blob:"))]

with sync_playwright() as p:
    b = p.chromium.launch()
    results = []
    for label, vp, scheme in [("desktop-light", {"width": 1280, "height": 1000}, "light"), ("mobile-dark", {"width": 390, "height": 844}, "dark")]:
        ctx = b.new_context(viewport=vp, color_scheme=scheme, timezone_id="Asia/Tokyo", locale="ja-JP", device_scale_factor=2 if "mobile" in label else 1, bypass_csp=True)
        page = ctx.new_page()
        errs, reqs = [], []
        page.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        page.on("request", lambda r: reqs.append(r.url))
        page.add_init_script(FILLTEXT_SPY)
        page.goto(URL)
        page.wait_for_function("document.getElementById('cardImg').src.startsWith('data:image/png')")
        if label == "desktop-light":
            # 画像の下端の行：左に URL（濃い緑・太め）、右に「作 @… ・ #…」（灰色・小さめ）。画像の大きさは 1080×1350 のまま
            ft = page.evaluate("window.__fillTextCalls.filter(c => c.w === 1080 && c.h === 1350 && c.y === 1350 - 64)")
            check("card footer calls (left, right)", [(c["s"], c["x"], c["align"]) for c in ft],
                  [("yuita-genecraft.github.io/tools/cc-tsuchihyo", 64, "left"), ("作 @yuita_Genecraft ・ #ClaudeCode通知表", 1080 - 64, "right")])
            check("card footer styles (url bold green / right small gray)", [(c["font"].split(" ")[0], c["font"].split(" ")[1], c["color"].lower()) for c in ft],
                  [("bold", "21px", "#2e6a4e"), ("500", "17px", "#5a6b64")])   # canvas は 700 を bold・色を小文字に直して返す
            check("card size", page.evaluate("[...new Set(window.__fillTextCalls.map(c => c.w + 'x' + c.h))].includes('1080x1350')"), True)
            share = page.input_value("#shareText")
            check("share text hashtag equals card footer hashtag", "#ClaudeCode通知表 via @yuita_Genecraft" in share.split("\n"), True)
        page.screenshot(path=str(SHOTS / f"sample-{label}.png"), full_page=True)
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        print(f"[{label}] horizontal overflow: {overflow}")
        check(f"{label} horizontal overflow", overflow, False)
        if label == "desktop-light":
            src = page.get_attribute("#cardImg", "src")
            (SHOTS / "card-sample.png").write_bytes(base64.b64decode(src.split(",", 1)[1]))
            page.set_input_files("#fileInput", files)
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのログ'", timeout=20000)
            cur = page.evaluate("JSON.parse(JSON.stringify(window.__tsuchihyo.current))")
            ok = True
            for k in ("prompts", "interrupts", "rejects", "images", "lines", "bad", "activeDays", "nightDays", "streak", "nightPrompts", "tokens", "compacts", "limitHits", "apiErrors"):
                ok &= check(k, cur[k], expect[k])
            ok &= check("usd", round(cur["usd"], 9), round(expect["usd"], 9))
            ok &= check("workMin", round(cur["workMin"], 6), round(expect["workMin"], 6))
            ok &= check("workMinUnion", round(cur["workMinUnion"], 6), round(expect["workMinUnion"], 6))
            ok &= check("politeRatio", round(cur["politeRatio"], 9), round(expect["politeRatio"], 9))
            for k, v in expect["you"].items():
                ok &= check("you." + k, cur["you"][k], v)
            for k, v in expect["claude"].items():
                ok &= check("claude." + k, cur["claude"][k], v)
            ok &= check("period", (cur["period"]["start"], cur["period"]["end"]), expect["period"])
            ok &= check("tools", dict(cur["toolsTop"]), expect["tools"])
            for m in cur["models"]:
                e = expect["models"][m["model"]]
                ok &= check(f"model {m['model']} usd", round(m["usd"], 9), round(e["usd"], 9))
                ok &= check(f"model {m['model']} estimated", m["estimated"], e["estimated"])
            print("bash", cur["bashTop"], "exts", cur["extsTop"], "slash", cur["slashTop"], "subjects", [(s["label"], s["count"], s["grade"]) for s in cur["subjects"]])
            print("sessions", cur["sessions"], "longestMin", cur["longestSessionMin"], "projects", cur["projectsTop"])
            print("ALL MATCH" if ok else "MISMATCH")
            page.screenshot(path=str(SHOTS / "mine-desktop-light.png"), full_page=True)
            src = page.get_attribute("#cardImg", "src")
            (SHOTS / "card-mine.png").write_bytes(base64.b64decode(src.split(",", 1)[1]))
            print("share text:\n" + page.input_value("#shareText"))
            st = page.input_value("#shareText")
            check("share text via once at the tag line", (st.count("via @yuita_Genecraft"), "#ClaudeCode通知表 via @yuita_Genecraft" in st.split("\n")), (1, True))
            check("author line in colophon", page.eval_on_selector_all(".colophon a[href='https://x.com/yuita_Genecraft']", "e => e.length"), 1)
            # フォルダ選択（~/.claude 相当を丸ごと＝history.jsonl も混ざる）
            page.click("#resetBtn")
            page.set_input_files("#dirInput", str(HERE / "logs"))
            page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのログ'", timeout=20000)
            cur2 = page.evaluate("({files: window.__tsuchihyo.current.files, prompts: window.__tsuchihyo.current.prompts, lines: window.__tsuchihyo.current.lines, usd: window.__tsuchihyo.current.usd})")
            print("dir input:", cur2)
            if extra:
                page.click("#resetBtn")
                page.set_input_files("#fileInput", extra)
                page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのログ'", timeout=60000)
                cur3 = page.evaluate("JSON.parse(JSON.stringify(window.__tsuchihyo.current))")
                exp3 = ref.run([pathlib.Path(f) for f in extra])
                for k in ("prompts", "interrupts", "rejects", "tokens", "compacts", "limitHits", "apiErrors"):
                    check("real " + k, cur3[k], exp3[k])
                check("real usd", round(cur3["usd"], 6), round(exp3["usd"], 6))
                print("real models", [(m["model"], m["calls"], round(m["usd"], 4)) for m in cur3["models"]])
                print("real tools", cur3["toolsTop"][:8])
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
    print("[csp] img src data:", (page.get_attribute("#cardImg", "src") or "")[:22])
    page.set_input_files("#fileInput", files)
    page.locator("#statusPill", has_text="あなたのログ").wait_for(timeout=20000)
    print("[csp] status:", page.locator("#statusText").text_content())
    print("[csp] errors:", errs)
    print("[csp] non-data requests:", [r for r in reqs if not r.startswith("data:")])
    check("csp browser errors", errs, [])
    check("csp external requests", external_requests(reqs), [])
    ctx.close()
    b.close()

# 公開先の URL つきの build：共有文の URL の行と、画像の下端の URL が同じ物か
PUB = "https://yuita-genecraft.github.io/tools/cc-tsuchihyo/"
subprocess.run([sys.executable, str(HERE.parent / "build_standalone.py"), str(APP / "app.html"), str(APP / "dist" / "pub.html"), "--url", PUB], check=True)
with sync_playwright() as p2:
    b2 = p2.chromium.launch(); pg = b2.new_context(bypass_csp=True).new_page(); pg.add_init_script(FILLTEXT_SPY)
    pg.goto((APP / "dist" / "pub.html").as_uri())
    pg.wait_for_function("document.getElementById('cardImg').src.startsWith('data:image/png')")
    share_lines = pg.input_value("#shareText").split("\n")
    left = pg.evaluate("window.__fillTextCalls.filter(c => c.h === 1350 && c.y === 1286 && c.align === 'left').map(c => c.s)")
    check("pub build: card URL == share text URL line without scheme", (share_lines[-1], left), (PUB, [PUB.replace("https://", "").rstrip("/")]))
    b2.close()

print(f"CHECK FAILURES: {failures}")
sys.exit(1 if failures else 0)
