"""Actual browser import/export, CSP, responsive UI and shared CLI/page parsing."""
import json, os, pathlib, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOTS = ROOT / 'test/shots'
SHOTS.mkdir(exist_ok=True)
subprocess.run([sys.executable, str(ROOT / 'build_standalone.py'), str(ROOT / 'cc-seizon/app.html'), str(ROOT / 'cc-seizon/dist/index.html')], check=True)
subprocess.run([sys.executable, str(ROOT / 'test/gen_seizon.py')], check=True)
URL = (ROOT / 'cc-seizon/dist/index.html').as_uri()
count = 0
def check(value, label):
    global count
    assert value, label
    count += 1
    print('OK', label, flush=True)

with sync_playwright() as pw, tempfile.TemporaryDirectory(prefix='logmap-e2e-') as temp:
    tmp = pathlib.Path(temp)
    browser = pw.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH'))
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, timezone_id='Asia/Tokyo')
    page = context.new_page(); errors = []; requests = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: requests.append(r.url))
    page.goto(URL); page.wait_for_selector('.lab-score')
    check(page.evaluate('window.__seizon.tab') == 'lab', 'default is change lab')
    check('架空' in page.text_content('#statusPill'), 'sample is visibly marked')
    check('架空' in page.evaluate('window.__logmapLab.reportText()'), 'sample marker survives text export')
    check(page.evaluate('document.querySelector("meta[http-equiv=Content-Security-Policy]").content.includes("connect-src \'none\'")'), 'no-network CSP retained')
    before = page.evaluate('JSON.stringify(window.__logmapLab.result)')
    with page.expect_download() as save:
        page.click('#labSave')
    saved = tmp / 'sample.json'; save.value.save_as(saved)
    doc = json.loads(saved.read_text())
    check(doc['data']['sample'] and len(doc['sha256']) == 64, 'snapshot carries sample/provenance')
    page.select_option('#labTool', 'codex')
    check(page.evaluate('window.__logmapLab.result.before.n') < json.loads(before)['before']['n'], 'AI filter changes both sides')
    page.set_input_files('#labFile', str(saved))
    page.wait_for_function('() => window.__logmapLab.state.tool === ""')
    check(page.evaluate('JSON.stringify(window.__logmapLab.result)') == before, 'restoring JSON exactly reproduces report')
    broken = dict(doc); broken['sha256'] = '0' * 64
    (tmp / 'bad.json').write_text(json.dumps(broken))
    page.set_input_files('#labFile', str(tmp / 'bad.json'))
    page.wait_for_function('() => document.querySelector("#labMessage").textContent.includes("読み込めません")')
    check(page.evaluate('JSON.stringify(window.__logmapLab.result)') == before, 'invalid snapshot preserves previous report')
    with page.expect_download() as image:
        page.click('#labImage')
    image.value.save_as(tmp / 'card.png')
    check((tmp / 'card.png').stat().st_size > 10000, 'card is generated from current result')
    page.set_input_files('#labFile', str(saved))
    page.wait_for_function('() => document.querySelector("#labMessage").textContent.includes("内容の一致")')
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(SHOTS / 'lab-desktop.png'), full_page=True)
    page.screenshot(path=str(SHOTS / 'lab-first-screen.png'))
    for width in (390, 768, 320):
        page.set_viewport_size({'width': width, 'height': 844})
        check(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'no horizontal overflow {width}px')
        check(page.locator('#labSave').is_visible(), f'export controls visible {width}px')
        if width == 390:
            page.screenshot(path=str(SHOTS / 'lab-mobile.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.goto(URL)
    page.locator('#importDrawer').evaluate('e => e.open = true')
    page.set_input_files('#logInput', str(ROOT / 'test/seizon/logs4'))
    page.wait_for_function('() => window.__seizon.labData.sample === false')
    check(page.evaluate('window.__seizon.labData.rows.length') == 9, 'real logs replace sample, no synthetic fallback')
    data_browser = page.evaluate('JSON.parse(JSON.stringify(window.__seizon.labData))')
    out, html = tmp / 'fixture.json', tmp / 'report.html'
    cmd = ['node', str(ROOT / 'cc-seizon/collect.mjs'), '--logs', str(ROOT / 'test/seizon/logs4'), '--out', str(out), '--html', str(html), '--pivot', '2026-09-21T00:00:00Z', '--days', '7', '--change', '</script><img onerror=alert(1)>']
    cp = subprocess.run(cmd, capture_output=True, text=True)
    check(cp.returncode == 0, 'local collector completes')
    cli = json.loads(out.read_text())
    for field in ('rows', 'sessions', 'compactions', 'coverage'):
        check(data_browser[field] == cli['data'][field], f'CLI and browser have identical {field}')
    check((out.stat().st_mode & 0o777) == 0o600, 'private report file mode')
    original = out.read_bytes()
    cp2 = subprocess.run(cmd, capture_output=True, text=True)
    check(cp2.returncode != 0 and out.read_bytes() == original, 'existing output is never overwritten')
    page.goto(html.as_uri())
    page.wait_for_function('() => window.__seizon.labData.sample === false')
    check(page.evaluate('window.__logmapLab.result.before.n') == 6, 'offline report boots with actual data')
    check(page.evaluate('window.__logmapLab.result.after.n') == 2, 'offline report retains sidechain exclusion')
    check(page.evaluate('document.querySelectorAll("img[onerror]").length') == 0, 'change label cannot escape inline bootstrap')
    check('保存データ' == page.text_content('#statusPill'), 'offline report identifies stored data')
    page.select_option('#labTool', 'codex')
    check(page.evaluate('window.__logmapLab.result.deltaPoints') is None, 'missing baseline is not a zero-percent baseline')
    check(not errors, f'no browser exceptions: {errors}')
    check(not [u for u in requests if not u.startswith(('file:', 'data:', 'blob:'))], 'zero external requests')
    browser.close()
print(f'{count} checks passed')
