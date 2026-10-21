#!/usr/bin/env python3
"""生存率のテスト用に、Claude Code 形式のログ（JSONL）と、突き合わせるプロジェクトのフォルダを作る。
境界ケースを意図して混ぜる。手で数えた期待値は test/e2e_seizon.py の HAND にある。"""
import json, pathlib, shutil

HERE = pathlib.Path(__file__).parent / "seizon"
LOGS = HERE / "logs" / "projects"
PROJ = HERE / "proj" / "alpha"
for d in (HERE / "logs", HERE / "logs2", HERE / "logs3", HERE / "logs4", HERE / "proj"):
    if d.exists():
        shutil.rmtree(d)

n = 0
def U():
    global n
    n += 1
    return f"00000000-0000-4000-8000-{n:012d}"

ALPHA = "/Users/t/dev/alpha"
BETA = "/Users/t/dev/beta"

def asst(block, ts, sid="s1", cwd=ALPHA, mid="msg", out=100, **kw):
    o = {"parentUuid": None, "isSidechain": False, "userType": "external", "cwd": cwd, "sessionId": sid, "version": "2.1.0", "type": "assistant", "requestId": "req_" + mid,
         "message": {"id": mid, "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [block], "stop_reason": None,
                     "usage": {"input_tokens": 10, "output_tokens": out, "cache_read_input_tokens": 1000}},
         "uuid": U(), "timestamp": ts}
    o.update(kw)
    return o

def user_text(text, ts, sid="s1", cwd=ALPHA, as_list=False):
    """最初の指示（頼み方の節で使う）。content は文字列か text ブロックの配列（text をリストで渡すと複数ブロック）"""
    content = [{"type": "text", "text": t} for t in (text if isinstance(text, list) else [text])] if as_list or isinstance(text, list) else text
    return {"parentUuid": None, "isSidechain": False, "userType": "external", "cwd": cwd, "sessionId": sid, "version": "2.1.0", "type": "user",
            "message": {"role": "user", "content": content}, "uuid": U(), "timestamp": ts}

def result(tool_id, ts, text, tur=None, is_error=False, sid="s1", cwd=ALPHA):
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": text}
    if is_error:
        block["is_error"] = True
    o = {"parentUuid": None, "isSidechain": False, "userType": "external", "cwd": cwd, "sessionId": sid, "version": "2.1.0", "type": "user",
         "message": {"role": "user", "content": [block]}, "uuid": U(), "timestamp": ts}
    if tur is not None:
        o["toolUseResult"] = tur
    return o

def use(name, tid, inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}

def numbered(text, sep="→"):
    return "\n".join(f"{i + 1:6d}{sep}{l}" for i, l in enumerate(text.split("\n")))

# ---------- ファイルの中身 ----------
A_V1 = "import { db } from './db';\nexport function listNotes(userId: string) {\n  return db.notes.where({ userId }).toArray();\n}\nexport function countNotes() {\n  return db.notes.count();\n}\n"
A_OLD = "  return db.notes.where({ userId }).toArray();"
A_NEW = "  return db.notes.where({ userId }).sortBy('updatedAt');"
A_NOW = "import { db } from './db';\nexport function listNotes(userId: string) {\n  return db.notes.where({ userId }).sortBy('updatedAt');\n}\nexport function countNotes(userId: string) {\n  return db.notes.count();\n}\n"

B_V0 = "export const VERSION = '1.0.0';\nexport function hello(name: string) {\n  return `hello ${name}`;\n}\n"
B_OLD = "export function hello(name: string) {\n  return `hello ${name}`;\n}"
B_NEW = B_OLD + "\n\nexport function bye(name: string) {\n  return `bye ${name}`;\n}"
B_NOW = "export const VERSION = '1.0.0';\n" + B_NEW + "\n"

C_ORIG = "const a = 1;\nconst b = 2;\n"
C_V1 = "const a = 1;\nconst b = 2;\nconst c = a + b;\nexport default function sum(list: number[]) {\n  return list.reduce((x, y) => x + y, 0);\n}\n"
C_NOW = "const a = 1;\nconst b = 2;\nconst c = a + b;\nexport default function sum(list: number[]) {\n  return list.reduce((x, y) => x + y, 0) + 0;\n}\n"

GONE_V1 = "export function oldSync() {\n  const notes = fetchAllNotesWithoutPaging();\n  return notes.length;\n}\nexport const LEGACY = true;\n"

MULTI_V0 = "export const config = {\n  retries: 3,\n  timeout: 1000,\n};\n"
MULTI_NOW = "export const config = {\n  retries: 5,\n  backoff: 'linear',\n  timeout: 1000,\n};\n"

NEVER = "export const NEVER = 'written by human actually';\nexport const N2 = 2;\n"
WS_V1 = "const x = 1;\nconst y = 2;\n}\nab\n----\n} else {\n  break;\n</div>\nreturn;\n"
WS_NOW = "const  x  = 1;\nconst y = 2;\n}\n} else {\n"
WIN_V1 = "export const WIN = 1;\nexport const WIN2 = 2;\n"
WIN_NOW = "export const WIN = 1;\r\nexport const WIN2 = 2;\r\nexport const WIN = 1;\r\n"   # 同じ行が2回＝1つに数える
SEC_V1 = 'export const API_KEY = "sk-abcdefghijklmnop12345678";\nexport const endpointForNotesServiceV2 = "https://example.com/api/v2/notes";\n'
D_V0 = "const d1 = 1;\nconst d2 = 2;"
D_V1 = "const d1 = 1;\nconst d2 = 2;\nconst d3 = 3;\n"

# ---------- ログ s1（alpha・2026-09-01 JST 23:00〜） ----------
S1 = []
# 最初の指示（s1）。s1 の assistant は 12 通・出力 100 ずつ＝1,200 トークン
# /clear の記録とその出力は指示ではない＝最初の指示は次の行（頼み方の節の first）
S1.append(user_text("<command-name>/clear</command-name>\n            <command-message>clear</command-message>\n            <command-args></command-args>", "2026-09-01T13:58:00.000Z"))
S1.append(user_text("<local-command-stdout></local-command-stdout>", "2026-09-01T13:58:01.000Z"))
S1.append(user_text("a.ts に listNotes を足して、並びは updatedAt にして", "2026-09-01T13:59:00.000Z"))
S1.append(asst(use("Write", "w_a", {"file_path": f"{ALPHA}/src/a.ts", "content": A_V1}), "2026-09-01T14:00:00.000Z", mid="m1"))
S1.append(result("w_a", "2026-09-01T14:00:10.000Z", f"File created successfully at: {ALPHA}/src/a.ts", {"type": "create", "filePath": f"{ALPHA}/src/a.ts", "content": A_V1, "structuredPatch": []}))
# 1つの応答（message.id＝m2）が content block ごとに別の行＝thinking の行と tool_use の行。usage は同じ（100）＝応答ごとに1回だけ数える（Codex の指摘・PR #17）
S1.append(asst({"type": "thinking", "thinking": "a.ts を直す", "signature": "x"}, "2026-09-01T14:00:59.000Z", mid="m2"))
S1.append(asst(use("Edit", "e_a1", {"file_path": f"{ALPHA}/src/a.ts", "old_string": A_OLD, "new_string": A_NEW}), "2026-09-01T14:01:00.000Z", mid="m2"))
S1.append(result("e_a1", "2026-09-01T14:01:05.000Z", "The file has been updated.", {"filePath": f"{ALPHA}/src/a.ts", "oldString": A_OLD, "newString": A_NEW, "originalFile": A_V1, "structuredPatch": [], "userModified": False, "replaceAll": False}))
# 失敗した Edit（old_string が無い）＝数えない
S1.append(asst(use("Edit", "e_a2", {"file_path": f"{ALPHA}/src/a.ts", "old_string": "nonexistent", "new_string": "export const ERR = 1;"}), "2026-09-01T14:02:00.000Z", mid="m3"))
S1.append(result("e_a2", "2026-09-01T14:02:05.000Z", "<tool_use_error>String to replace not found in file.</tool_use_error>", is_error=True))
# b.ts：Read（toolUseResult に中身）→ old 側に元からある行を含む Edit
S1.append(asst(use("Read", "r_b", {"file_path": f"{ALPHA}/src/b.ts"}), "2026-09-01T14:03:00.000Z", mid="m4"))
S1.append(result("r_b", "2026-09-01T14:03:05.000Z", numbered(B_V0.rstrip("\n")), {"type": "text", "file": {"filePath": f"{ALPHA}/src/b.ts", "content": B_V0, "numLines": 4, "startLine": 1, "totalLines": 4}}))
# 流れている途中の行＝先の text の行は output_tokens が小さい（3）・後の tool_use の行が最終（100）＝応答の最大を取る
S1.append(asst({"type": "text", "text": "b.ts を直します"}, "2026-09-01T14:03:59.000Z", mid="m5", out=3))
S1.append(asst(use("Edit", "e_b", {"file_path": f"{ALPHA}/src/b.ts", "old_string": B_OLD, "new_string": B_NEW}), "2026-09-01T14:04:00.000Z", mid="m5"))
S1.append(result("e_b", "2026-09-01T14:04:05.000Z", "The file has been updated.", {"filePath": f"{ALPHA}/src/b.ts", "oldString": B_OLD, "newString": B_NEW, "originalFile": B_V0, "structuredPatch": []}))
# c.ts：Read 無しの Write（update）＝originalFile の行は元からある
S1.append(asst(use("Write", "w_c", {"file_path": f"{ALPHA}/src/c.ts", "content": C_V1}), "2026-09-01T14:05:00.000Z", mid="m6"))
S1.append(result("w_c", "2026-09-01T14:05:05.000Z", "The file has been updated.", {"type": "update", "filePath": f"{ALPHA}/src/c.ts", "content": C_V1, "originalFile": C_ORIG, "structuredPatch": []}))
# gone.ts：作った後に1行を Claude が直し、ファイルごと人が消した
S1.append(asst(use("Write", "w_g", {"file_path": f"{ALPHA}/src/gone.ts", "content": GONE_V1}), "2026-09-01T14:06:00.000Z", mid="m7"))
S1.append(result("w_g", "2026-09-01T14:06:05.000Z", "File created successfully", {"type": "create", "filePath": f"{ALPHA}/src/gone.ts", "content": GONE_V1, "structuredPatch": []}))
S1.append(asst(use("Edit", "e_g", {"file_path": f"{ALPHA}/src/gone.ts", "old_string": "export const LEGACY = true;", "new_string": "export const LEGACY = false;"}), "2026-09-01T14:07:00.000Z", mid="m8"))
S1.append(result("e_g", "2026-09-01T14:07:05.000Z", "The file has been updated.", {"filePath": f"{ALPHA}/src/gone.ts", "oldString": "export const LEGACY = true;", "newString": "export const LEGACY = false;", "originalFile": GONE_V1}))
# multi.ts：Read → MultiEdit（2つ目の old が1つ目の new の行を含む＝Claude 自身の書き直し）
S1.append(asst(use("Read", "r_m", {"file_path": f"{ALPHA}/src/multi.ts"}), "2026-09-01T14:08:00.000Z", mid="m9"))
S1.append(result("r_m", "2026-09-01T14:08:05.000Z", numbered(MULTI_V0.rstrip("\n")), {"type": "text", "file": {"filePath": f"{ALPHA}/src/multi.ts", "content": MULTI_V0, "numLines": 4, "startLine": 1, "totalLines": 4}}))
S1.append(asst(use("MultiEdit", "me_m", {"file_path": f"{ALPHA}/src/multi.ts", "edits": [
    {"old_string": "  retries: 3,", "new_string": "  retries: 5,\n  backoff: 'exponential',"},
    {"old_string": "  backoff: 'exponential',", "new_string": "  backoff: 'linear',"}]}), "2026-09-01T14:08:30.000Z", mid="m10"))
S1.append(result("me_m", "2026-09-01T14:08:35.000Z", "Applied 2 edits to " + f"{ALPHA}/src/multi.ts", {"filePath": f"{ALPHA}/src/multi.ts", "edits": [], "originalFileContents": MULTI_V0, "structuredPatch": []}))
# never.ts：結果の記録が無い Write＝数えない（フォルダには同じ中身のファイルがある）
S1.append(asst(use("Write", "w_n", {"file_path": f"{ALPHA}/src/never.ts", "content": NEVER}), "2026-09-01T14:09:00.000Z", mid="m11"))
# 壊れた行（tool_use を含むが JSON ではない）
S1.append('{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/x"')
# ws.ts：数えない行（}・ab・----・} else {・break;・</div>・return;）を含む
S1.append(asst(use("Write", "w_ws", {"file_path": f"{ALPHA}/src/ws.ts", "content": WS_V1}), "2026-09-01T14:10:00.000Z", mid="m12"))
S1.append(result("w_ws", "2026-09-01T14:10:05.000Z", "File created successfully", {"type": "create", "filePath": f"{ALPHA}/src/ws.ts", "content": WS_V1}))
# re.ts：s1 が2行書き、2行目を自分で消す → s2 があとで同じ行を入れ直す（下）＝今ある RE2 の行は s2 のもの（Codex の指摘・PR #17）
RE_V1 = "export const RE = 1;\nexport const RE2 = 2;\n"
S1.append(asst(use("Write", "w_re", {"file_path": f"{ALPHA}/src/re.ts", "content": RE_V1}), "2026-09-01T14:11:00.000Z", mid="m20"))
S1.append(result("w_re", "2026-09-01T14:11:05.000Z", "File created successfully", {"type": "create", "filePath": f"{ALPHA}/src/re.ts", "content": RE_V1}))
S1.append(asst(use("Edit", "e_re1", {"file_path": f"{ALPHA}/src/re.ts", "old_string": "export const RE2 = 2;\n", "new_string": ""}), "2026-09-01T14:12:00.000Z", mid="m21"))
S1.append(result("e_re1", "2026-09-01T14:12:05.000Z", "The file has been updated.", {"filePath": f"{ALPHA}/src/re.ts", "oldString": "export const RE2 = 2;\n", "newString": "", "originalFile": RE_V1, "structuredPatch": []}))
# 短い行・summary 行・空行
S1.append({"type": "summary", "summary": "x", "leafUuid": "x"})
S1.append("")

# ---------- ログ s2（alpha・再開で s1 の先頭3行が写っている） ----------
# 再開で s1 の先頭（w_a とその結果・e_a1 の2行）が写っている＝uuid で重複を除く（sessionId は s1 のまま＝別の会話のまま）
i_wa = next(i for i, o in enumerate(S1) if isinstance(o, dict) and o["type"] == "assistant" and o["message"]["id"] == "m1")
i_ea = max(i for i, o in enumerate(S1) if isinstance(o, dict) and o["type"] == "assistant" and o["message"]["id"] == "m2")
S2 = list(S1[i_wa:i_ea + 1])
# 最初の指示（s2・<pasted_content> の中身＝タグを外して読む）。s2 の assistant は 6 通・出力 300 ずつ＝1,800 トークン（うち1通は別の場所 alpha-copy・1通は NotebookEdit）
S2.append(user_text('<pasted_content id="7e4d">引き継ぎ：win.ts・sec.ts・d.ts を足す。範囲外は触らない</pasted_content>', "2026-09-03T00:59:00.000Z", sid="s2", as_list=True))
S2.append(asst(use("Write", "w_win", {"file_path": f"{ALPHA}/src/win.ts", "content": WIN_V1}), "2026-09-03T01:00:00.000Z", sid="s2", mid="m13", out=300))
S2.append(result("w_win", "2026-09-03T01:00:05.000Z", "File created successfully", {"type": "create", "filePath": f"{ALPHA}/src/win.ts", "content": WIN_V1}, sid="s2"))
S2.append(asst(use("Write", "w_sec", {"file_path": f"{ALPHA}/src/sec.ts", "content": SEC_V1}), "2026-09-03T01:01:00.000Z", sid="s2", mid="m14", out=300))
S2.append(result("w_sec", "2026-09-03T01:01:05.000Z", "File created successfully", {"type": "create", "filePath": f"{ALPHA}/src/sec.ts", "content": SEC_V1}, sid="s2"))
# d.ts：Read の結果が番号つきの本文だけ（toolUseResult 無し）→ Write（toolUseResult 無し）
S2.append(asst(use("Read", "r_d", {"file_path": f"{ALPHA}/src/d.ts"}), "2026-09-03T01:02:00.000Z", sid="s2", mid="m15", out=300))
S2.append(result("r_d", "2026-09-03T01:02:05.000Z", numbered(D_V0), sid="s2"))
S2.append(asst(use("Write", "w_d", {"file_path": f"{ALPHA}/src/d.ts", "content": D_V1}), "2026-09-04T16:30:00.000Z", sid="s2", mid="m16", out=300))
S2.append(result("w_d", "2026-09-04T16:30:05.000Z", "The file has been updated.", sid="s2"))
# 別の場所にある同名プロジェクト（root の多数決で負ける）
S2.append(asst(use("Edit", "e_decoy", {"file_path": "/Users/t/other/alpha-copy/src/a.ts", "old_string": "", "new_string": "export const DECOY = 1;"}), "2026-09-04T16:40:00.000Z", sid="s2", mid="m17", out=300))
S2.append(result("e_decoy", "2026-09-04T16:40:05.000Z", "The file has been updated.", sid="s2"))
# NotebookEdit は拾わない
# re.ts：s1 が消した RE2 の行を s2 が入れ直す＝RE2 は s2 の行（s2 の alpha の行は 6・別の場所に 1＝按分 6/7）
S2.append(asst(use("Edit", "e_re2", {"file_path": f"{ALPHA}/src/re.ts", "old_string": "export const RE = 1;\n", "new_string": "export const RE = 1;\nexport const RE2 = 2;\n"}), "2026-09-04T16:35:00.000Z", sid="s2", mid="m22", out=300))
S2.append(result("e_re2", "2026-09-04T16:35:05.000Z", "The file has been updated.", {"filePath": f"{ALPHA}/src/re.ts", "oldString": "export const RE = 1;\n", "newString": "export const RE = 1;\nexport const RE2 = 2;\n", "originalFile": "export const RE = 1;\n", "structuredPatch": []}, sid="s2"))
S2.append(asst(use("NotebookEdit", "nb", {"notebook_path": f"{ALPHA}/nb.ipynb", "new_source": "print(1)"}), "2026-09-04T16:41:00.000Z", sid="s2", mid="m18", out=300))
S2.append(result("nb", "2026-09-04T16:41:05.000Z", "ok", sid="s2"))

# ---------- ログ s3（beta＝別プロジェクト） ----------
S3 = []
S3.append(user_text("beta の x.ts を作って", "2026-09-01T23:59:00.000Z", sid="s3", cwd=BETA))
S3.append(asst(use("Write", "w_beta", {"file_path": f"{BETA}/src/x.ts", "content": "export const beta = 1;\nexport const gamma = 2;\n"}), "2026-09-02T00:00:00.000Z", sid="s3", cwd=BETA, mid="m19", out=50))
S3.append(result("w_beta", "2026-09-02T00:00:05.000Z", "File created successfully", {"type": "create", "filePath": f"{BETA}/src/x.ts", "content": "export const beta = 1;\nexport const gamma = 2;\n"}, sid="s3", cwd=BETA))

def write_log(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n")

write_log(LOGS / "-Users-t-dev-alpha" / "s1.jsonl", S1)
write_log(LOGS / "-Users-t-dev-alpha" / "s2.jsonl", S2)
write_log(LOGS / "-Users-t-dev-beta" / "s3.jsonl", S3)
write_log(LOGS.parent / "history.jsonl", [{"display": "hi", "pastedContents": {}, "timestamp": 1756700000000, "project": ALPHA}])

# ---------- プロジェクトのフォルダ（今の中身） ----------
def put(rel, data):
    p = PROJ / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        p.write_bytes(data)
    else:
        p.write_bytes(data.encode("utf-8"))

put("src/a.ts", A_NOW)
put("src/b.ts", B_NOW)
put("src/c.ts", C_NOW)
put("src/multi.ts", MULTI_NOW)
put("src/never.ts", NEVER)
put("src/ws.ts", WS_NOW)
put("src/win.ts", WIN_NOW)
put("src/sec.ts", SEC_V1)
put("src/d.ts", D_V1)
put("src/re.ts", "export const RE = 1;\nexport const RE2 = 2;\n")   # RE＝s1 の行・RE2＝s2 が入れ直した行（どちらも残っている）
put("src/human.ts", "export const h1 = 1;\nexport const h2 = 2;\nexport const h3 = 3;\n")
put("README.md", "# alpha\n\nA small project.\n")
# 読まないもの
put("node_modules/left-pad/index.js", "module.exports = s => s;\n")
put("dist/bundle.js", "console.log('built');\n")
put("package-lock.json", "{\n  \"name\": \"alpha\"\n}\n")
put("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
put("src/blob.ts", "export const z = 1;\x00\x00binary\n")

# ---------- 直し癖（habits）：別のログ置き場 logs2 と別プロジェクト proj/habits（alpha の手計算を動かさない） ----------
# 照合は hunk 方式（app.html の analyzeHabits のコメント）。手で数えた期待値＝e2e_seizon.py の HAND_HABITS
#   h1：Claude が app.ts を Write（11行）。人が直した今の中身：
#     1 import の引用符 "→'           → hunk（前の目印なし・次=2）窓に1行 → 似ている → quote
#     2 export function run(...)        残った（目印）
#     3 console.log("run start")        → 消えた。hunk（2〜4）窓は空 → debug
#     4 const items = normalize(input)  残った（目印）
#     5 // call the api                 → 消えた。hunk（4〜6）窓は空・前後がコード行 → comment
#     6 const res = api.call(items)     残った（目印）
#     7 console.log("run end", res)     → 消えた（quick＝デバッグ出力）
#     8 let total = 0                   → let sum = 0            ┐ 7〜10 が1つの hunk（前=6・次=目印なし＝末尾まで）
#     9 for (...) total += x            → for (...) sum += x     │ 似ている行なし → quick を除くコード3行＝窓の残り3行 → 順番で組 → rename ×3（total → sum）
#    10 return total                    → return sum             ┘ console は debug
#    11 }                               数えない行
#   h2：Claude が util.ts を Write（8行）。人が直した今の中身：
#     1 export function fmt(n: any): string {   → n: number（any）。hunk（前なし・次=2）窓に1行・似ている
#     2 const prefix = "#"                       残った
#     3 const label = "Total count"              → "合計"（string）。hunk（2〜4）窓に1行・似ている（const・label が共通）
#     4 const suffix = "!"                       残った
#     5 console.log("fmt", n)                    → 消えた（debug）。hunk（4〜6）窓は空
#     6 return prefix + label + String(n) + suffix   残った
#     7 }                                        数えない行
#     8 export const UNUSED = 1                  → 消えた。hunk（前=6・次なし）窓は空 → delete（コードの1行＝型にならない）
#   h3：Claude が old.ts を Write（5行）→ 人が丸ごと書き直し（5行とも無い・今の中身は別物4行）＝前後の目印なし
#     → 窓なし（全体から厳しめ）→ 似ている行なし → 5行まとめて消えた（コード≥2）→ block ×5
#   → lines=18（app 7＋util 4＋old 5＋tool 2）・matched=8（quote1＋rename3＋any1＋string1＋import1＋other1）
#   → debug 3回・2セッション・2ファイル＝候補 ／ rename 3回・1セッション（total → sum が3回）＝参考 ／ any・comment・import・quote・string 各1＝参考 ／ block 5・delete 1・other 1＝型にならない
#   → written 26（app 10＋util 7＋old 5＋tool 4・数えない行 } を除く）・alive 8（app 3＋util 3＋tool 2）・human 18・rewritten 0・dropped 0
HAB = "/Users/t/dev/habits"
LOGS2 = HERE / "logs2" / "projects"
PROJ2 = HERE / "proj" / "habits"
APP_V1 = ('import { api } from "./api";\n'
          'export function run(input: number[]) {\n'
          '  console.log("run start");\n'
          '  const items = normalize(input);\n'
          '  // call the api\n'
          '  const res = api.call(items);\n'
          '  console.log("run end", res);\n'
          '  let total = 0;\n'
          '  for (const x of res) total += x;\n'
          '  return total;\n'
          '}\n')
APP_NOW = ("import { api } from './api';\n"
           'export function run(input: number[]) {\n'
           '  const items = normalize(input);\n'
           '  const res = api.call(items);\n'
           '  let sum = 0;\n'
           '  for (const x of res) sum += x;\n'
           '  return sum;\n'
           '}\n')
UTIL_V1 = ('export function fmt(n: any): string {\n'
           '  const prefix = "#";\n'
           '  const label = "Total count";\n'
           '  const suffix = "!";\n'
           '  console.log("fmt", n);\n'
           '  return prefix + label + String(n) + suffix;\n'
           '}\n'
           'export const UNUSED = 1;\n')
UTIL_NOW = ('export function fmt(n: number): string {\n'
            '  const prefix = "#";\n'
            '  const label = "合計";\n'
            '  const suffix = "!";\n'
            '  return prefix + label + String(n) + suffix;\n'
            '}\n')
OLD_V1 = ('export class LegacyCache {\n'
          '  private store = new Map<string, string>();\n'
          '  get(key: string) { return this.store.get(key); }\n'
          '  set(key: string, v: string) { this.store.set(key, v); }\n'
          '  clear() { this.store.clear(); }\n'
          '}\n')
OLD_NOW = ('export function makeCache() {\n'
           '  const m = new Map();\n'
           '  return { read: (k) => m.get(k), write: (k, v) => m.set(k, v) };\n'
           '}\n')
def hw(tid, path, content, ts, sid, mid):
    return [asst(use("Write", tid, {"file_path": path, "content": content}), ts, sid=sid, cwd=HAB, mid=mid),
            result(tid, ts[:-8] + "05.000Z", "File created successfully", {"type": "create", "filePath": path, "content": content}, sid=sid, cwd=HAB)]
write_log(LOGS2 / "-Users-t-dev-habits" / "h1.jsonl", [user_text("app.ts を書いて", "2026-09-10T09:59:00.000Z", sid="h1", cwd=HAB)] + hw("hw_app", f"{HAB}/src/app.ts", APP_V1, "2026-09-10T10:00:00.000Z", "h1", "hm1"))
write_log(LOGS2 / "-Users-t-dev-habits" / "h2.jsonl", [user_text("util.ts を書いて", "2026-09-12T09:59:00.000Z", sid="h2", cwd=HAB)] + hw("hw_util", f"{HAB}/src/util.ts", UTIL_V1, "2026-09-12T10:00:00.000Z", "h2", "hm2"))
write_log(LOGS2 / "-Users-t-dev-habits" / "h3.jsonl", [user_text("キャッシュをとりあえず作って", "2026-09-13T09:59:00.000Z", sid="h3", cwd=HAB)] + hw("hw_old", f"{HAB}/src/old.ts", OLD_V1, "2026-09-13T10:00:00.000Z", "h3", "hm3"))
#   h4：Claude が tool.py を Write（4行）。Python の import は引用符のパスが無い（Codex の指摘・PR #15）
#     1 from oldpkg.utils import foo   → from newpkg.utils import foo（モジュールが変わった＝import）。hunk（前なし・次=2）
#     2 VALUE = 1                       残った
#     3 from pkg import a               → from pkg import a, b（名前の追加＝other）。hunk（2〜4）
#     4 print(VALUE)                    残った
TOOL_V1 = "from oldpkg.utils import foo\nVALUE = 1\nfrom pkg import a\nprint(VALUE)\n"
TOOL_NOW = "from newpkg.utils import foo\nVALUE = 1\nfrom pkg import a, b\nprint(VALUE)\n"
# system-reminder のブロックが先にあっても、指示は次のブロック
H4 = [user_text(["<system-reminder>\nCLAUDE.md を読みました\n</system-reminder>", "tool.py を作って"], "2026-09-14T09:59:00.000Z", sid="h4", cwd=HAB)] + hw("hw_tool", f"{HAB}/src/tool.py", TOOL_V1, "2026-09-14T10:00:00.000Z", "h4", "hm4")
write_log(LOGS2 / "-Users-t-dev-habits" / "h4.jsonl", H4)
#   h5：h4 を --resume した会話。本物のログと同じく、h4 の message が同じ uuid・新しい sessionId（h5）で写っている → 同じ会話にまとめ、写った分は1回だけ数える
#     その後 extra.py を Write（1行・残存）。→ 会話 h4＋h5＝書いた 5（tool 4＋extra 1）・残った 3・出力 100＋100＝200・再開 1 回
H5 = []
for o in H4:
    c = dict(o); c["sessionId"] = "h5"; H5.append(c)   # uuid はそのまま
H5 += hw("hw_extra", f"{HAB}/src/extra.py", "EXTRA = True\n", "2026-09-14T11:00:00.000Z", "h5", "hm5")
write_log(LOGS2 / "-Users-t-dev-habits" / "h5.jsonl", H5)
def put2(rel, data):
    p = PROJ2 / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8"))
put2("src/app.ts", APP_NOW)
put2("src/util.ts", UTIL_NOW)
put2("src/old.ts", OLD_NOW)
put2("src/tool.py", TOOL_NOW)
put2("src/extra.py", "EXTRA = True\n")
put2("README.md", "# habits\n")


# ---------- Codex と Gemini（Antigravity）のログ（logs3）・プロジェクト multi ----------
# 手で数えた期待値は e2e_seizon.py の HAND_MULTI。
MULTI = "/Users/t/dev/multi"
LOGS3 = HERE / "logs3"
PROJ3 = HERE / "proj" / "multi"
X_V1 = "export const one = 1;\nexport const two = 2;\nexport const three = 3;\nexport const four = 4;\n"
#   Codex：x.ts を作る（4行）→ unified_diff で two を消して five を足す。今の x.ts＝one・three・five・人が足した行（four は人が消した）
#   → 書いた 5（one two three four five）・残った 3・自分で書き直し 1（two）・人が消した 1（four）
X_DIFF = "--- a/src/x.ts\n+++ b/src/x.ts\n@@ -1,4 +1,4 @@\n export const one = 1;\n-export const two = 2;\n export const three = 3;\n export const four = 4;\n+export const five = 5;\n"
X_NOW = "export const one = 1;\nexport const three = 3;\nexport const five = 5;\nexport const human = 'h';\n"
def cx(ts, typ, payload):
    return {"timestamp": ts, "type": typ, "payload": payload}
CX = [cx("2026-10-01T09:00:00.000Z", "session_meta", {"id": "cx-1", "cwd": MULTI, "originator": "codex_cli_rs"}),
      cx("2026-10-01T09:00:01.000Z", "event_msg", {"type": "item_completed", "item": {"type": "UserMessage", "id": "u1", "content": [{"type": "text", "text": "x.ts を作って"}]}}),
      cx("2026-10-01T09:00:05.000Z", "event_msg", {"type": "item_completed", "item": {"type": "FileChange", "id": "fc1", "status": "completed", "changes": {f"{MULTI}/src/x.ts": {"type": "add", "content": X_V1}}}}),
      #   使用量：応答ごと。input はキャッシュ分（cached）を含む＝入力 200・キャッシュ 800。出力 50＋70＝120（同じ response_id の2行目は数えない）
      cx("2026-10-01T09:00:06.000Z", "token_usage_record", {"response_id": "r1", "usage": {"input_tokens": 1000, "cached_input_tokens": 800, "cache_write_input_tokens": 0, "output_tokens": 50}}),
      cx("2026-10-01T09:00:06.500Z", "token_usage_record", {"response_id": "r1", "usage": {"input_tokens": 1000, "cached_input_tokens": 800, "cache_write_input_tokens": 0, "output_tokens": 50}}),
      cx("2026-10-01T09:10:00.000Z", "event_msg", {"type": "item_completed", "item": {"type": "CommandExecution", "id": "ce1", "command": "ls"}}),
      cx("2026-10-01T09:20:00.000Z", "event_msg", {"type": "item_completed", "item": {"type": "FileChange", "id": "fc2", "status": "completed", "changes": {"src/x.ts": {"type": "update", "unified_diff": X_DIFF, "move_path": None}}}}),
      #   失敗した変更は数えない
      cx("2026-10-01T09:21:00.000Z", "event_msg", {"type": "item_completed", "item": {"type": "FileChange", "id": "fc3", "status": "failed", "changes": {"src/x.ts": {"type": "add", "content": "export const failed = 0;\n"}}}}),
      cx("2026-10-01T09:20:01.000Z", "token_usage_record", {"response_id": "r2", "usage": {"input_tokens": 500, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 70}})]
write_log(LOGS3 / "codex" / "sessions" / "2026" / "10" / "01" / "rollout-2026-10-01T09-00-00-cx-1.jsonl", CX)
#   Gemini：y.py を write_to_file（4行）→ replace_file_content で return 'one' を return 'uno' に。今の y.py＝その4行
#   → 書いた 5・残った 4・自分で書き直し 1（return 'one'）。出力 30＋40＋10＋0＝80（重ねて残った step は1回）
#   同じ step が 3 か所に重ねて残る（transcript.jsonl・chunks/transcript・chunks/transcript_full）。main の step 2 は tool_calls が切られている＝full を使う。
#   chunks の写しは値が JSON の文字列でもう一段包まれている。step 4 は main にしか無く切られている（ほどけない）＝数えず、読めなかった編集 1件
CONV = "11111111-2222-4333-8444-555555555555"
G1 = "def first():\n    return 'one'\ndef third():\n    return 'three'\n"
G_REP_OLD = "def first():\n    return 'one'\n"
G_REP_NEW = "def first():\n    return 'uno'\n"
G_NOW = "def first():\n    return 'uno'\ndef third():\n    return 'three'\n"
YP = f"{MULTI}/src/y.py"
def gstep(i, typ, ts, **kw):
    o = {"step_index": i, "type": typ, "source": "MODEL", "status": "DONE", "created_at": ts}
    o.update(kw); return o
def wcall(path, content, q=False):
    a = {"TargetFile": path, "CodeContent": content, "Overwrite": "true", "Description": "x", "toolAction": "w", "toolSummary": "w"}
    if q: a = {k: json.dumps(v) for k, v in a.items()}
    return {"name": "write_to_file", "args": a}
def rcall(path, old, new, q=False):
    a = {"TargetFile": path, "TargetContent": old, "ReplacementContent": new, "StartLine": 1, "EndLine": 2, "AllowMultiple": False, "Instruction": "x", "Description": "x", "toolAction": "r", "toolSummary": "r"}
    if q: a = {k: (json.dumps(v) if isinstance(v, str) else v) for k, v in a.items()}
    return {"name": "replace_file_content", "args": a}
s0 = gstep(0, "USER_INPUT", "2026-10-02T10:00:00Z", content="<USER_REQUEST>\ny.py を作って\n</USER_REQUEST>")
s1 = gstep(1, "PLANNER_RESPONSE", "2026-10-02T10:00:10Z", content="作ります", input_tokens=300, output_tokens=30, cache_read_tokens=1000, tool_calls=[{"name": "run_command", "args": {"CommandLine": "ls", "Cwd": MULTI}}])
s2 = gstep(2, "PLANNER_RESPONSE", "2026-10-02T10:01:00Z", content="", input_tokens=400, output_tokens=40, cache_read_tokens=2000, tool_calls=[wcall(YP, G1)])
s2_cut = dict(s2, truncated_fields=["tool_calls"], tool_calls=[wcall(YP, G1[:20])])
s3 = gstep(3, "PLANNER_RESPONSE", "2026-10-02T10:02:00Z", content="", input_tokens=100, output_tokens=10, cache_read_tokens=0, tool_calls=[rcall(YP, G_REP_OLD, G_REP_NEW)])
s4_cut = gstep(4, "PLANNER_RESPONSE", "2026-10-02T10:03:00Z", content="", input_tokens=0, output_tokens=0, cache_read_tokens=0, truncated_fields=["tool_calls"],
               tool_calls=[{"name": "write_to_file", "args": {"TargetFile": json.dumps(YP), "CodeContent": '"def cut(', "Overwrite": '"true"'}}])
#   step 5：本文が " で始まる値（包まれていない）＝そのまま数える（Codex の指摘 PR #20：値の頭の " で包まれたと決めない）。書いた 2・残った 2
ZP = f"{MULTI}/src/z.js"
Z_NOW = '"use strict";\nconst zed = 1;\n'
s5 = gstep(5, "PLANNER_RESPONSE", "2026-10-02T10:04:00Z", content="", input_tokens=0, output_tokens=0, cache_read_tokens=0, tool_calls=[wcall(ZP, Z_NOW)])
GB = LOGS3 / "gemini" / "antigravity" / "brain" / CONV / ".system_generated" / "logs"
write_log(GB / "transcript.jsonl", [s0, s1, s2_cut, s3, s4_cut, s5])
write_log(GB / "chunks" / "transcript" / "00000000.jsonl", [s0, s1, dict(s3, tool_calls=[rcall(YP, G_REP_OLD, G_REP_NEW, q=True)])])
write_log(GB / "chunks" / "transcript_full" / "00000000.jsonl", [s1, dict(s2, tool_calls=[wcall(YP, G1, q=True)])])
def put3(rel, data):
    p = PROJ3 / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8"))
put3("src/x.ts", X_NOW)
put3("src/y.py", G_NOW)
put3("src/z.js", Z_NOW)
put3("README.md", "# multi\n")


# ---------- 文脈とトークン（logs4・プロジェクトは要らない） ----------
# 手で数えた期待値は e2e_seizon.py の HAND_TOKENS。文脈＝入力＋キャッシュ読み＋キャッシュ書き込み
LOGS4 = HERE / "logs4"
def tk(ts, mid, inp, cr, cw, out=100, sid="t1", side=False, cw1h=None):
    u = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}
    if cw1h is not None:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": cw - cw1h, "ephemeral_1h_input_tokens": cw1h}
    return {"parentUuid": None, "isSidechain": side, "userType": "external", "cwd": "/Users/t/dev/tok", "sessionId": sid, "version": "2.1.0", "type": "assistant",
            "message": {"id": mid, "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "ok"}], "usage": u},
            "uuid": U(), "timestamp": ts}
T1 = [tk("2026-09-20T09:00:00.000Z", "tm1", 3, 0, 30000),            # 文脈 30,003（〜5万）
      tk("2026-09-20T09:05:00.000Z", "tm2", 3, 30000, 140000),       # 170,003（15〜20万）
      tk("2026-09-20T09:05:01.000Z", "tm2", 3, 30000, 140000, out=40),   # 同じ応答の途中の行＝1回
      tk("2026-09-20T09:10:00.000Z", "tm3", 3, 170000, 50000),       # 220,003（20〜40万）
      tk("2026-09-20T10:00:00.000Z", "tm6", 3, 0, 100, out=10, side=True),   # サブエージェント（103・〜5万）＝再開の判定には入れない
      #   2時間あけて再開：読めたのは 1万（前の文脈 220,003 の 2割未満）・書き込み 20万（半分超）＝検出条件に一致
      tk("2026-09-20T11:10:00.000Z", "tm4", 3, 10000, 200000, cw1h=200000),   # 210,003（20〜40万）
      #   3時間あけて再開：キャッシュが読めている＝一致しない
      tk("2026-09-20T14:10:00.000Z", "tm5", 3, 200000, 5000)]        # 205,003（20〜40万）
write_log(LOGS4 / "projects" / "-Users-t-dev-tok" / "t1.jsonl", T1)
CX4 = [cx("2026-09-21T09:00:00.000Z", "session_meta", {"id": "cx-t", "cwd": "/Users/t/dev/tok"}),
       cx("2026-09-21T09:00:05.000Z", "token_usage_record", {"response_id": "tr1", "usage": {"input_tokens": 160000, "cached_input_tokens": 150000, "cache_write_input_tokens": 0, "output_tokens": 50}}),   # 160,000
       #   2時間あけて、キャッシュが読めていない（Codex はキャッシュ書き込みが記録に無い＝一致しない。再開としては数える）
       cx("2026-09-21T11:00:05.000Z", "token_usage_record", {"response_id": "tr2", "usage": {"input_tokens": 170000, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 60}})]   # 170,000
write_log(LOGS4 / "codex" / "sessions" / "2026" / "09" / "21" / "rollout-2026-09-21T09-00-00-cx-t.jsonl", CX4)
