#!/usr/bin/env python3
"""生存率のテスト用に、Claude Code 形式のログ（JSONL）と、突き合わせるプロジェクトのフォルダを作る。
境界ケースを意図して混ぜる。手で数えた期待値は test/e2e_seizon.py の HAND にある。"""
import json, pathlib, shutil

HERE = pathlib.Path(__file__).parent / "seizon"
LOGS = HERE / "logs" / "projects"
PROJ = HERE / "proj" / "alpha"
for d in (HERE / "logs", HERE / "proj"):
    if d.exists():
        shutil.rmtree(d)

n = 0
def U():
    global n
    n += 1
    return f"00000000-0000-4000-8000-{n:012d}"

ALPHA = "/Users/t/dev/alpha"
BETA = "/Users/t/dev/beta"

def asst(block, ts, sid="s1", cwd=ALPHA, mid="msg", **kw):
    o = {"parentUuid": None, "isSidechain": False, "userType": "external", "cwd": cwd, "sessionId": sid, "version": "2.1.0", "type": "assistant", "requestId": "req_" + mid,
         "message": {"id": mid, "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [block], "stop_reason": None,
                     "usage": {"input_tokens": 10, "output_tokens": 100}},
         "uuid": U(), "timestamp": ts}
    o.update(kw)
    return o

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
WIN_NOW = "export const WIN = 1;\r\nexport const WIN2 = 2;\r\n"
SEC_V1 = 'export const API_KEY = "sk-abcdefghijklmnop12345678";\nexport const endpointForNotesServiceV2 = "https://example.com/api/v2/notes";\n'
D_V0 = "const d1 = 1;\nconst d2 = 2;"
D_V1 = "const d1 = 1;\nconst d2 = 2;\nconst d3 = 3;\n"

# ---------- ログ s1（alpha・2026-09-01 JST 23:00〜） ----------
S1 = []
S1.append(asst(use("Write", "w_a", {"file_path": f"{ALPHA}/src/a.ts", "content": A_V1}), "2026-09-01T14:00:00.000Z", mid="m1"))
S1.append(result("w_a", "2026-09-01T14:00:10.000Z", f"File created successfully at: {ALPHA}/src/a.ts", {"type": "create", "filePath": f"{ALPHA}/src/a.ts", "content": A_V1, "structuredPatch": []}))
S1.append(asst(use("Edit", "e_a1", {"file_path": f"{ALPHA}/src/a.ts", "old_string": A_OLD, "new_string": A_NEW}), "2026-09-01T14:01:00.000Z", mid="m2"))
S1.append(result("e_a1", "2026-09-01T14:01:05.000Z", "The file has been updated.", {"filePath": f"{ALPHA}/src/a.ts", "oldString": A_OLD, "newString": A_NEW, "originalFile": A_V1, "structuredPatch": [], "userModified": False, "replaceAll": False}))
# 失敗した Edit（old_string が無い）＝数えない
S1.append(asst(use("Edit", "e_a2", {"file_path": f"{ALPHA}/src/a.ts", "old_string": "nonexistent", "new_string": "export const ERR = 1;"}), "2026-09-01T14:02:00.000Z", mid="m3"))
S1.append(result("e_a2", "2026-09-01T14:02:05.000Z", "<tool_use_error>String to replace not found in file.</tool_use_error>", is_error=True))
# b.ts：Read（toolUseResult に中身）→ old 側に元からある行を含む Edit
S1.append(asst(use("Read", "r_b", {"file_path": f"{ALPHA}/src/b.ts"}), "2026-09-01T14:03:00.000Z", mid="m4"))
S1.append(result("r_b", "2026-09-01T14:03:05.000Z", numbered(B_V0.rstrip("\n")), {"type": "text", "file": {"filePath": f"{ALPHA}/src/b.ts", "content": B_V0, "numLines": 4, "startLine": 1, "totalLines": 4}}))
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
# 短い行・summary 行・空行
S1.append({"type": "summary", "summary": "x", "leafUuid": "x"})
S1.append("")

# ---------- ログ s2（alpha・再開で s1 の先頭3行が写っている） ----------
S2 = S1[:3]
S2 = list(S2)
S2.append(asst(use("Write", "w_win", {"file_path": f"{ALPHA}/src/win.ts", "content": WIN_V1}), "2026-09-03T01:00:00.000Z", sid="s2", mid="m13"))
S2.append(result("w_win", "2026-09-03T01:00:05.000Z", "File created successfully", {"type": "create", "filePath": f"{ALPHA}/src/win.ts", "content": WIN_V1}, sid="s2"))
S2.append(asst(use("Write", "w_sec", {"file_path": f"{ALPHA}/src/sec.ts", "content": SEC_V1}), "2026-09-03T01:01:00.000Z", sid="s2", mid="m14"))
S2.append(result("w_sec", "2026-09-03T01:01:05.000Z", "File created successfully", {"type": "create", "filePath": f"{ALPHA}/src/sec.ts", "content": SEC_V1}, sid="s2"))
# d.ts：Read の結果が番号つきの本文だけ（toolUseResult 無し）→ Write（toolUseResult 無し）
S2.append(asst(use("Read", "r_d", {"file_path": f"{ALPHA}/src/d.ts"}), "2026-09-03T01:02:00.000Z", sid="s2", mid="m15"))
S2.append(result("r_d", "2026-09-03T01:02:05.000Z", numbered(D_V0), sid="s2"))
S2.append(asst(use("Write", "w_d", {"file_path": f"{ALPHA}/src/d.ts", "content": D_V1}), "2026-09-04T16:30:00.000Z", sid="s2", mid="m16"))
S2.append(result("w_d", "2026-09-04T16:30:05.000Z", "The file has been updated.", sid="s2"))
# 別の場所にある同名プロジェクト（root の多数決で負ける）
S2.append(asst(use("Edit", "e_decoy", {"file_path": "/Users/t/other/alpha-copy/src/a.ts", "old_string": "", "new_string": "export const DECOY = 1;"}), "2026-09-04T16:40:00.000Z", sid="s2", mid="m17"))
S2.append(result("e_decoy", "2026-09-04T16:40:05.000Z", "The file has been updated.", sid="s2"))
# NotebookEdit は拾わない
S2.append(asst(use("NotebookEdit", "nb", {"notebook_path": f"{ALPHA}/nb.ipynb", "new_source": "print(1)"}), "2026-09-04T16:41:00.000Z", sid="s2", mid="m18"))
S2.append(result("nb", "2026-09-04T16:41:05.000Z", "ok", sid="s2"))

# ---------- ログ s3（beta＝別プロジェクト） ----------
S3 = []
S3.append(asst(use("Write", "w_beta", {"file_path": f"{BETA}/src/x.ts", "content": "export const beta = 1;\nexport const gamma = 2;\n"}), "2026-09-02T00:00:00.000Z", sid="s3", cwd=BETA, mid="m19"))
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
put("src/human.ts", "export const h1 = 1;\nexport const h2 = 2;\nexport const h3 = 3;\n")
put("README.md", "# alpha\n\nA small project.\n")
# 読まないもの
put("node_modules/left-pad/index.js", "module.exports = s => s;\n")
put("dist/bundle.js", "console.log('built');\n")
put("package-lock.json", "{\n  \"name\": \"alpha\"\n}\n")
put("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
put("src/blob.ts", "export const z = 1;\x00\x00binary\n")
put("big.log", "x" * (1600 * 1024))

print("ok", sorted(str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file()))
