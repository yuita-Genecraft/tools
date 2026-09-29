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

def check(name, got, want, tol=1e-9):
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print(("OK  " if ok else "NG  ") + f"{name}: got={got} want={want}")
    return ok

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
        page.goto(URL)
        page.wait_for_function("document.getElementById('cardImg').src.startsWith('data:image/png')")
        page.screenshot(path=str(SHOTS / f"sample-{label}.png"), full_page=True)
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        print(f"[{label}] horizontal overflow: {overflow}")
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
        ctx.close()
    # CSP を効かせたまま：エラーなし・画像が出る・ファイルが読める・外部通信なし
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, timezone_id="Asia/Tokyo", locale="ja-JP")
    page = ctx.new_page(); errs = []; reqs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: reqs.append(r.url))
    page.goto(URL)
    page.locator("#statusPill", has_text="見本").wait_for()
    print("[csp] img src data:", (page.get_attribute("#cardImg", "src") or "")[:22])
    page.set_input_files("#fileInput", files)
    page.locator("#statusPill", has_text="あなたのログ").wait_for(timeout=20000)
    print("[csp] status:", page.locator("#statusText").text_content())
    print("[csp] errors:", errs)
    print("[csp] non-data requests:", [r for r in reqs if not r.startswith("data:")])
    ctx.close()
    b.close()
