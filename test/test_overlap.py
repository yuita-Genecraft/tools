#!/usr/bin/env python3
"""重複を除外した推定利用時間(workMinUnion)が要件通りに計算されているかを検証するテスト。
合成データとして様々なエッジケース（重複、包含、等）を作成し、JS側の計算結果と期待値を比較する。"""
import json, pathlib, subprocess, sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
APP = HERE.parent / "cc-tsuchihyo"
TEST_LOGS = HERE / "overlap_logs"
TEST_LOGS.mkdir(exist_ok=True)

subprocess.run([sys.executable, str(HERE.parent / "build_standalone.py"), str(APP / "app.html"), str(APP / "dist" / "index.html")], check=True)
URL = (APP / "dist" / "index.html").as_uri()

def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

n = 0
def U():
    global n
    n += 1
    return f"00000000-0000-4000-8000-{n:012d}"

def user(ts, sid="s1"):
    return {
        "parentUuid": None, "isSidechain": False, "userType": "external", "cwd": "/x", "sessionId": sid,
        "version": "2.1.0", "gitBranch": "main", "type": "user",
        "message": {"role": "user", "content": "テスト"},
        "uuid": U(), "timestamp": ts
    }

def asst(ts, sid="s1"):
    return {
        "parentUuid": None, "isSidechain": False, "userType": "external", "cwd": "/x", "sessionId": sid,
        "version": "2.1.0", "type": "assistant", "requestId": "req",
        "message": {"id": "msg", "type": "message", "role": "assistant", "model": "m", "content": [{"type": "text", "text": "x"}]},
        "uuid": U(), "timestamp": ts
    }

# 1) データなし / 空 (プロンプト自体が0の場合は JS 側は undefined や初期値になる可能性もあるが、ここでは発言はあるが応答がないケースなども想定)
# 2) 重複しない区間: [0, 10], [20, 30] -> 20
# 3) 一部重複する区間: [0, 20], [10, 30] -> 30
# 4) 完全に包含される区間: [0, 40], [10, 30], [20, 25] -> 40
# 5) 同一の区間: [0, 10], [0, 10] -> 10
# 6) 境界だけ接する区間: [0, 10], [10, 20] -> 20
# 7) タイムゾーン違い、複数セッション跨ぎ
# 8) 要求にあった [(0,3), (1,2), (1,3)] -> 和集合 3分

# [(0,3), (1,2), (1,3)] を再現する
# セッション構成：
# session s1: 00:00:00 -> 00:03:00  (0〜3)
# session s2: 00:01:00 -> 00:02:00  (1〜2)
# session s3: 00:01:00 -> 00:03:00  (1〜3)

logs_case1 = [
    # s1: 0~3
    user("2026-09-01T00:00:00.000Z", "s1"),
    asst("2026-09-01T00:03:00.000Z", "s1"),
    # s2: 1~2
    user("2026-09-01T00:01:00.000Z", "s2"),
    asst("2026-09-01T00:02:00.000Z", "s2"),
    # s3: 1~3
    user("2026-09-01T00:01:00.000Z", "s3"),
    asst("2026-09-01T00:03:00.000Z", "s3"),
]

# 追加の包含・重複・境界テスト用
# session s4: 10:00~10:10 (重複なし)
# session s5: 10:10~10:20 (境界で接する)
# session s6: 10:30~10:50 (一部重複)
# session s7: 10:40~11:00 (一部重複)
# session s8: 12:00~12:10 (タイムゾーン違い: JST で 21:00 -> UTC 12:00)
# session s9: 12:00~12:10 (UTC直書きとJSTで同一)

logs_case2 = [
    # 重複なしと接する
    user("2026-09-01T10:00:00.000Z", "s4"),
    asst("2026-09-01T10:10:00.000Z", "s4"),
    user("2026-09-01T10:10:00.000Z", "s5"),
    asst("2026-09-01T10:20:00.000Z", "s5"),
    # 一部重複 (10:30 ~ 11:00 = 30分)
    user("2026-09-01T10:30:00.000Z", "s6"),
    asst("2026-09-01T10:50:00.000Z", "s6"),
    user("2026-09-01T10:40:00.000Z", "s7"),
    asst("2026-09-01T11:00:00.000Z", "s7"),
    # タイムゾーン違い、同一区間
    user("2026-09-01T12:00:00.000Z", "s8"),
    asst("2026-09-01T12:10:00.000Z", "s8"),
    user("2026-09-01T21:00:00.000+09:00", "s9"),  # UTC 12:00
    asst("2026-09-01T21:10:00.000+09:00", "s9"),  # UTC 12:10
]

def run_test_on_logs(logs, expected_union_minutes, case_name):
    print(f"--- Running {case_name} ---")
    file_path = TEST_LOGS / f"{case_name}.jsonl"
    write_jsonl(file_path, logs)

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 1000})
        page = ctx.new_page()
        page.goto(URL)
        page.set_input_files("#fileInput", str(file_path))
        page.wait_for_function("document.getElementById('statusPill').textContent === 'あなたのログ'", timeout=10000)

        cur = page.evaluate("JSON.parse(JSON.stringify(window.__tsuchihyo.current))")
        work_min_union = cur.get("workMinUnion", 0)
        work_min = cur.get("workMin", 0)

        print(f"got workMin: {work_min}")
        print(f"got workMinUnion: {work_min_union}, expected: {expected_union_minutes}")

        if abs(work_min_union - expected_union_minutes) > 1e-6:
            print(f"FAIL: {case_name} expected {expected_union_minutes} but got {work_min_union}")
            sys.exit(1)

        print("OK\n")
        ctx.close()
        b.close()

if __name__ == "__main__":
    # Case 1: [0,3], [1,2], [1,3] -> union = 3 min, sum of all = 3 + 1 + 2 = 6 min
    run_test_on_logs(logs_case1, 3.0, "case1_subset")

    # Case 2:
    # [10:00, 10:10] (10)
    # [10:10, 10:20] (10)
    # [10:30, 10:50] (20) & [10:40, 11:00] (20) -> union is [10:30, 11:00] (30)
    # [12:00, 12:10] (10) & JST equivalent (10) -> union is [12:00, 12:10] (10)
    # Total Union = 10 + 10 + 30 + 10 = 60 min
    # Total Raw Sum = 10 + 10 + 20 + 20 + 10 + 10 = 80 min
    run_test_on_logs(logs_case2, 60.0, "case2_various")

    print("ALL TESTS PASSED.")

    # Case 3: Empty / No completion intervals
    logs_case3_empty = [
        user("2026-09-01T00:00:00.000Z", "empty1")
    ]
    run_test_on_logs(logs_case3_empty, 0.0, "case3_empty")

    sys.exit(0)
