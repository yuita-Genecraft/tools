#!/usr/bin/env python3
"""生存率（cc-seizon/app.html）の別実装。ブラウザ版と同じ規則で、同じ数字が出るかを突き合わせるためのもの。
規則の正本は app.html のコメント。ここは写し（違いが出たらどちらかが間違い）。
使い方: run(log_paths, project_dir, strict=False) -> dict"""
import json, math, os, pathlib, re
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tokyo")   # e2e は Chromium のタイムゾーンを Asia/Tokyo にして揃える

# ---------- 行の正規化（app.html と同じ） ----------
WS = "[ \t\u000b\f\r   -     　﻿]"
RX_TRIM = re.compile("^" + WS + "+|" + WS + "+$")
RX_WS = re.compile(WS + "+")
RX_STRUCT = re.compile(r"^(?:[{}()\[\];,.:]|[ \t])*(?:else|try|finally|do|break|continue|return|pass|done|end|fi|esac|endif|default|then|begin|yield|next|catch)?(?:[{}()\[\];,.:]|[ \t])*$", re.I)
RX_CLOSE_TAG = re.compile(r"^<\/[A-Za-z][\w-]*>$")
TRIVIAL_MIN = 4

def utf16len(s):
    return len(s.encode("utf-16-le")) // 2

def norm_line(raw, strict):
    s = raw[:-1] if raw.endswith("\r") else raw
    if not strict:
        s = RX_WS.sub(" ", RX_TRIM.sub("", s.replace("\t", " ")))
    return s

def is_trivial(key):
    t = RX_TRIM.sub("", key)
    return utf16len(t) < TRIVIAL_MIN or not any(ch.isalnum() for ch in t) or bool(RX_STRUCT.match(t)) or bool(RX_CLOSE_TAG.match(t))

def line_keys(text, strict):
    out = []
    for raw in str(text).split("\n"):
        k = norm_line(raw, strict)
        if not is_trivial(k):
            out.append(k)
    return out

def norm_path(p):
    return str(p).replace("\\", "/")

# ---------- ログ ----------
USE_NAMES = {"Edit", "MultiEdit", "Write", "Read"}
RX_NUMBERED = re.compile(r"^\s*\d+(?:→|\t)")
LOG_SKIP_DIRS = {"node_modules", ".git", "plugins", "shell-snapshots", "statsig", "todos", "debug", "file-history", "session-env", "backups", "ide"}

def tool_result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(x.get("text", "") if isinstance(x, dict) and isinstance(x.get("text"), str) else "" for x in content)
    return ""

def parse_ts(s):
    if not isinstance(s, str):
        return None
    try:
        return int(round(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000))
    except ValueError:
        return None

def new_acc():
    return {"uses": {}, "results": {}, "files": 0, "lines": 0, "bad": 0, "sess": {}, "msgSid": {}, "resp": {}, "sessLink": []}

def resolve_sessions(acc):
    """app.html の resolveSessions と同じ：同じ uuid が別の sessionId で出たセッションを1つの会話にまとめる。代表＝いちばん早く始まった方（同時なら sid の文字列順）"""
    parent = {}
    def find(x):
        while x in parent and parent[x] != x:
            x = parent[x]
        return x
    for a, b in acc["sessLink"]:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups = {}
    for sid in acc["sess"]:
        groups.setdefault(find(sid), []).append(sid)
    rep_of, merged = {}, {}
    for sids in groups.values():
        sids.sort(key=lambda a: ((acc["sess"][a]["start"] if acc["sess"][a]["start"] is not None else float("inf")), a))
        rep = sids[0]
        m = {"out": 0, "inp": 0, "cache": 0, "msgs": 0, "first": "", "firstTs": None, "start": None, "end": None, "bash": 0, "cwd": "", "members": len(sids)}
        for sid in sids:
            v = acc["sess"][sid]; rep_of[sid] = rep
            m["out"] += v["out"]; m["inp"] += v["inp"]; m["cache"] += v["cache"]; m["msgs"] += v["msgs"]; m["bash"] += v["bash"]
            if v["firstTs"] is not None and (m["firstTs"] is None or v["firstTs"] < m["firstTs"]):
                m["firstTs"] = v["firstTs"]; m["first"] = v["first"]
            if v["start"] is not None and (m["start"] is None or v["start"] < m["start"]):
                m["start"] = v["start"]
            if v["end"] is not None and (m["end"] is None or v["end"] > m["end"]):
                m["end"] = v["end"]
            if not m["cwd"]:
                m["cwd"] = v["cwd"]
        merged[rep] = m
    return rep_of, merged

RX_TAG = re.compile(r"<[^<>]{1,80}>")
RX_RECORD = re.compile(r"^\s*<(command-name|command-message|command-args|local-command-stdout|local-command-caveat|system-reminder)\b")

def prompt_head(text):
    if RX_RECORD.match(text):
        return ""
    t = re.sub(r"\s+", " ", RX_TAG.sub(" ", str(text))).strip()
    return t[:100] + "…" if len(t) > 100 else t

def sess_of(acc, sid):
    s = acc["sess"].get(sid)
    if s is None:
        s = {"out": 0, "inp": 0, "cache": 0, "msgs": 0, "first": "", "firstTs": None, "start": None, "end": None, "bash": 0, "cwd": ""}
        acc["sess"][sid] = s
    return s

def handle_line(line, acc):
    acc["lines"] += 1
    if utf16len(line) < 40:
        return
    if '"message"' not in line:
        return
    try:
        o = json.loads(line)
    except ValueError:
        acc["bad"] += 1
        return
    if not isinstance(o, dict) or not isinstance(o.get("message"), dict):
        return
    sid = o["sessionId"] if isinstance(o.get("sessionId"), str) else ""
    ts_raw = parse_ts(o.get("timestamp"))
    if sid and ts_raw is not None:
        sv = sess_of(acc, sid)
        if sv["start"] is None or ts_raw < sv["start"]:
            sv["start"] = ts_raw
        if sv["end"] is None or ts_raw > sv["end"]:
            sv["end"] = ts_raw
        if not sv["cwd"] and isinstance(o.get("cwd"), str):
            sv["cwd"] = norm_path(o["cwd"])
    c = o["message"].get("content")
    if o.get("type") == "user" and sid and not o.get("isSidechain"):
        sv = sess_of(acc, sid)
        h = ""
        if isinstance(c, str):
            h = prompt_head(c)
        elif isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                    h = prompt_head(b["text"])
                    if h:
                        break
        if h and ts_raw is not None and (sv["firstTs"] is None or ts_raw < sv["firstTs"]):
            sv["first"] = h; sv["firstTs"] = ts_raw
    if not isinstance(c, list):
        return
    if o.get("type") == "assistant":
        ts = ts_raw
        # 使用トークンは応答（message.id）ごとに1回＝block ごとに分かれた行は最大を取る。写し（同じ uuid・別の sessionId）は数えず、会話をつなぐ
        uid = o["uuid"] if isinstance(o.get("uuid"), str) else ""
        mid = o["message"]["id"] if isinstance(o["message"].get("id"), str) else ("u:" + uid if uid else "")
        seen_sid = acc["msgSid"].get(uid) if uid else None
        if sid and seen_sid is not None and seen_sid != sid:
            acc["sessLink"].append((seen_sid, sid))
        if sid and mid and seen_sid is None:
            if uid:
                acc["msgSid"][uid] = sid
            r = acc["resp"].get(mid)
            if r is not None and r["sid"] != sid:
                acc["sessLink"].append((r["sid"], sid))
            else:
                sv = sess_of(acc, sid)
                if r is None:
                    r = {"sid": sid, "out": 0, "inp": 0, "cache": 0}; acc["resp"][mid] = r; sv["msgs"] += 1
                u = o["message"].get("usage")
                if isinstance(u, dict):
                    for k, v in (("out", u.get("output_tokens")), ("inp", u.get("input_tokens")),
                                 ("cache", (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0))):
                        n = v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0
                        if n > r[k]:
                            sv[k] += n - r[k]; r[k] = n
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                        sv["bash"] += 1
        for b in c:
            if not isinstance(b, dict) or b.get("type") != "tool_use" or b.get("name") not in USE_NAMES or not isinstance(b.get("id"), str):
                continue
            if b["id"] in acc["uses"]:
                continue
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            acc["uses"][b["id"]] = {"id": b["id"], "name": b["name"], "input": inp, "ts": ts,
                                    "sid": o["sessionId"] if isinstance(o.get("sessionId"), str) else "",
                                    "cwd": norm_path(o["cwd"]) if isinstance(o.get("cwd"), str) else ""}
    elif o.get("type") == "user":
        for b in c:
            if not isinstance(b, dict) or b.get("type") != "tool_result" or not isinstance(b.get("tool_use_id"), str):
                continue
            if b["tool_use_id"] in acc["results"]:
                continue
            text = tool_result_text(b.get("content"))
            t = o.get("toolUseResult")
            tur = None
            if isinstance(t, dict):
                tur = {}
                if isinstance(t.get("type"), str):
                    tur["type"] = t["type"]
                if isinstance(t.get("originalFile"), str):
                    tur["originalFile"] = t["originalFile"]
                elif isinstance(t.get("originalFileContents"), str):
                    tur["originalFile"] = t["originalFileContents"]
                if isinstance(t.get("file"), dict) and isinstance(t["file"].get("content"), str):
                    tur["file"] = {"content": t["file"]["content"]}
            acc["results"][b["tool_use_id"]] = {"isError": b.get("is_error") is True, "text": text if RX_NUMBERED.match(text) else "", "tur": tur}

def read_content(res):
    f = (res["tur"] or {}).get("file") if res["tur"] else None
    if isinstance(f, dict) and isinstance(f.get("content"), str):
        return f["content"]
    t = res["text"] or ""
    if not RX_NUMBERED.match(t):
        return ""
    return "\n".join(RX_NUMBERED.sub("", l, count=1) for l in t.split("\n"))

def read_log_file(path, acc):
    text = path.read_bytes().decode("utf-8", errors="replace")
    if text.startswith("﻿"):
        text = text[1:]
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    for line in parts:
        handle_line(line, acc)
    acc["files"] += 1

# ---------- 適用 ----------
def build_events(acc):
    evs = [u for u in acc["uses"].values() if u["ts"] is not None]
    evs.sort(key=lambda u: (u["ts"], u["id"]))
    for i, e in enumerate(evs):
        e["seq"] = i   # 同じ Edit／Write で入った行は seq が同じ（直し癖の hunk 用）
    return evs

def apply_events(evs, acc, strict):
    claude, known = {}, {}
    def known_add(p, keys):
        known.setdefault(p, set()).update(keys)
    def claude_add(p, k, ev):
        m = claude.setdefault(p, {})
        if k in m:
            rec = m[k]
            if rec["removed"]:   # 消えた行の入れ直し＝今ある行はその時のもの
                rec["ts"] = ev["ts"]; rec["sid"] = ev["sid"]; rec["seq"] = ev["seq"]
            rec["removed"] = False
        else:
            m[k] = {"ts": ev["ts"], "sid": ev["sid"], "seq": ev["seq"], "removed": False}
    def claude_remove(p, k):
        rec = claude.get(p, {}).get(k)
        if rec:
            rec["removed"] = True
    def apply_edit(p, old_s, new_s, ev):
        # 並びを保つ（JS の Set と同じ挿入順）＝直し癖の hunk は Claude が書いた順に依存する。set() だと PYTHONHASHSEED で順が変わる
        old_k, new_k = dict.fromkeys(line_keys(old_s, strict)), dict.fromkeys(line_keys(new_s, strict))
        for k in new_k:
            if k not in old_k:
                claude_add(p, k, ev)
        for k in old_k:
            if k not in new_k:
                claude_remove(p, k)
        known_add(p, new_k)
    applied = []
    for ev in evs:
        res = acc["results"].get(ev["id"])
        inp = ev["input"]
        p = norm_path(inp["file_path"]) if isinstance(inp.get("file_path"), str) else ""
        if not p:
            continue
        if ev["name"] == "Read":
            if res and not res["isError"]:
                t = read_content(res)
                if t:
                    known_add(p, line_keys(t, strict))
            continue
        if not res or res["isError"]:
            continue
        if ev["name"] in ("Edit", "MultiEdit") and res["tur"] and isinstance(res["tur"].get("originalFile"), str):
            known_add(p, line_keys(res["tur"]["originalFile"], strict))
        if ev["name"] == "Edit":
            if not isinstance(inp.get("new_string"), str):
                continue
            apply_edit(p, inp["old_string"] if isinstance(inp.get("old_string"), str) else "", inp["new_string"], ev)
        elif ev["name"] == "MultiEdit":
            if not isinstance(inp.get("edits"), list):
                continue
            for e in inp["edits"]:
                if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                    apply_edit(p, e["old_string"] if isinstance(e.get("old_string"), str) else "", e["new_string"], ev)
        elif ev["name"] == "Write":
            if not isinstance(inp.get("content"), str):
                continue
            cur = dict.fromkeys(line_keys(inp["content"], strict))   # 並びを保つ
            pre = set(known.get(p, set()))
            tur = res["tur"]
            if tur and tur.get("type") == "create":
                pre = set()
            elif tur and isinstance(tur.get("originalFile"), str):
                pre.update(line_keys(tur["originalFile"], strict))
            for k in cur:
                if k not in pre:
                    claude_add(p, k, ev)
            for k, rec in claude.get(p, {}).items():
                if k not in cur:
                    rec["removed"] = True
            known[p] = set(cur)
        else:
            continue
        applied.append({"path": p, "ts": ev["ts"], "sid": ev["sid"], "name": ev["name"], "cwd": ev["cwd"]})
    return claude, applied

def base_name(p):
    return p.split("/")[-1] or p

def find_root(claude, project, cwds, project_name):
    # 一致したファイルの数 → cwd そのもの → cwd の上 → 短い方 → 文字列順（app.html と同じ）
    by_base = {}
    for rel in project:
        by_base.setdefault(base_name(rel), []).append(rel)
    votes = {}
    for p in claude:
        for rel in by_base.get(base_name(p), []):
            if len(p) > len(rel) and p.endswith("/" + rel):
                root = p[: len(p) - len(rel) - 1]
                votes[root] = votes.get(root, 0) + 1
    def rank(root):
        if root in cwds:
            return 2
        return 1 if any(c.startswith(root + "/") for c in cwds) else 0
    best, best_n, best_rank = None, 0, -1
    for root, n in votes.items():
        r = rank(root)
        if best is None or n > best_n or (n == best_n and (r > best_rank or (r == best_rank and (len(root) < len(best) or (len(root) == len(best) and root < best))))):
            best, best_n, best_rank = root, n, r
    ambiguous = any(root != best and n == best_n and rank(root) == best_rank for root, n in votes.items())
    src = "files" if best else ""
    if not best:
        same = [c for c, _ in sorted(cwds.items(), key=lambda e: (-e[1], e[0])) if project_name and base_name(c) == project_name]
        if len(same) == 1:
            best, src = same[0], "cwd"
    return best, best_n, len(votes), ambiguous, src

RX_SECRET = re.compile(r"(sk|pk|ghp|gho|ghs|xox[abp]|AKIA|AIza)[-_A-Za-z0-9]{8,}|-----BEGIN|api[_-]?key|secret|token|passw|Bearer\s|[A-Za-z0-9+/=]{32,}|[0-9a-f]{32,}", re.I)

def pick_example(cands):
    ok = [c for c in cands if 12 <= utf16len(c["key"]) <= 72 and not RX_SECRET.search(c["key"])]
    ok.sort(key=lambda c: (-utf16len(c["key"]), c["key"], c["file"]))
    return ok[0] if ok else None

def date_key(ms):
    d = datetime.fromtimestamp(ms / 1000, TZ)
    return f"{d.year}-{d.month:02d}-{d.day:02d}"

def days_between(a, b):
    y1, m1, d1 = map(int, a.split("-")); y2, m2, d2 = map(int, b.split("-"))
    return (datetime(y2, m2, d2) - datetime(y1, m1, d1)).days

def alias_of(i):
    s = ""
    i += 1
    while i > 0:
        r = (i - 1) % 26
        s = chr(65 + r) + s
        i = (i - 1) // 26
    return s

RX_EXT = re.compile(r"\.([A-Za-z0-9]{1,8})$")

def assign_aliases(R):
    i = 0
    for f in R["files"]:
        if f["written"] > 0:
            m = RX_EXT.search(f["file"]); f["alias"] = "ファイル" + alias_of(i) + (("." + m.group(1)) if m else ""); i += 1
        else:
            f["alias"] = ""
    for f in R["missingFiles"]:
        m = RX_EXT.search(f["file"]); f["alias"] = "ファイル" + alias_of(i) + (("." + m.group(1)) if m else ""); i += 1

# ---------- 直し癖（app.html の analyzeHabits と同じ規則） ----------
RX_TOK = re.compile(r"[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`")
RX_DEBUG = re.compile(r"\b(console\.(log|debug|info|warn|error|trace)|print\s*\(|println!?\s*\(|System\.out\.print|fmt\.Print|dbg!|var_dump\s*\(|debugger;?$)")
RX_CJK = re.compile(r"[぀-ヿ㐀-鿿]")
HASH_COMMENT_EXT = {"py", "rb", "sh", "bash", "zsh", "yml", "yaml", "toml", "pl", "r", "ps1", "cfg", "ini", "conf", "env", "mk", "make", "dockerfile"}
RX_IMPORT = re.compile(r"^(import\s|from\s\S+\simport\s|export\s.+\sfrom\s|(const|let|var)\s.+=\s*require\s*\()")
RX_IDENT = re.compile(r"^[A-Za-z_$][\w$]*$"); RX_NUMTOK = re.compile(r"^\d+(?:\.\d+)?$"); RX_STRTOK = re.compile(r"^['\"`]")
RX_COMMENT_START = re.compile(r"^(//|/\*|\*\s|\*$|<!--|--\s)")
HABIT_LABELS = {"debug": "デバッグ出力の削除", "comment": "コメントの削除", "delete": "行の削除（置き換え無し）", "quote": "引用符の統一", "semi": "セミコロンの有無",
                "const": "const 化", "any": "any の型付け", "commentLang": "コメントの言語", "import": "import のパス・拡張子", "rename": "名前の変更",
                "string": "文字列（文言）の変更", "number": "数値の変更", "other": "その他の書き換え", "block": "まとまった削除・書き直し（3行以上）"}
HABIT_GENERIC = {"delete", "other", "block"}

def tokens_of(key):
    return RX_TOK.findall(key)

def is_comment_line(key, ext):
    if RX_COMMENT_START.search(key):
        return True
    return key.startswith("#") and not key.startswith("#!") and ext in HASH_COMMENT_EXT

HABIT_KIND = {"debug": "style", "comment": "style", "quote": "style", "semi": "style", "const": "style", "any": "style", "commentLang": "style", "import": "style",
              "rename": "content", "string": "content", "number": "content"}

def fmt_n(n):
    return f"{n:,}"

def habit_rule(hid, d, count):
    return {
        "debug": lambda: "デバッグ用の出力（console.log など）は残さない。",
        "comment": lambda: "説明のコメントは足さない。コードで分かることはコメントに書かない。",
        "quote": lambda: "文字列の引用符は " + ('"（ダブル）' if d == '"' else "'（シングル）") + " で統一する。",
        "semi": lambda: "文末のセミコロンを付ける。" if d == ";" else "文末のセミコロンは付けない。",
        "const": lambda: "再代入しない変数は const で宣言する。",
        "any": lambda: "any を使わない。型が決まらなければ unknown か具体的な型を書く。",
        "commentLang": lambda: "コメントは日本語で書く。" if d == "ja" else "コメントは英語で書く。",
        "import": lambda: "import のパスと拡張子は、既存ファイルの書き方に合わせる。",
        "rename": lambda: f"名前を後で変えた行が{fmt_n(count)}回" + (f"（例：{d}）" if d else "") + "。命名は先に決めて渡すか、既存の名前に合わせるよう書いておく。",
        "string": lambda: f"文言（メッセージ・テストの説明）を後で直した行が{fmt_n(count)}回。文言は仕様や既存の文に合わせ、決まっていない所は仮置きと明記させる。",
        "number": lambda: f"数値（上限・件数・待ち時間）を後で直した行が{fmt_n(count)}回。数値は既存の設定値や定数から引かせる。",
    }[hid]()

def import_module(s):
    m = re.match(r"^from\s+(\S+)\s+import\s", s)
    if m:
        return m.group(1)
    return re.sub(r"\s+", "", re.sub(r"\s+as\s+[A-Za-z_]\w*", "", re.sub(r"^import\s+", "", s)))   # 別名は識別子だけ外す（「, 」は残す）

def classify_pair(before, after, ext):
    if after is None:
        if RX_DEBUG.search(before):
            return "debug", ""
        if is_comment_line(before, ext):
            return "comment", ""
        return "delete", ""
    if before.replace('"', "'") == after.replace('"', "'"):
        return "quote", ('"' if '"' in after else "'")
    if re.sub(r";\s*$", "", before) == re.sub(r";\s*$", "", after):
        return "semi", (";" if re.search(r";\s*$", after) else "")
    if re.match(r"^(var|let)\s", before) and re.match(r"^const\s", after) and re.sub(r"^(var|let)\s", "", before) == re.sub(r"^const\s", "", after):
        return "const", ""
    tb, ta = tokens_of(before), tokens_of(after)
    if "any" in tb and "any" not in ta:
        return "any", ""
    if is_comment_line(before, ext) and is_comment_line(after, ext) and bool(RX_CJK.search(before)) != bool(RX_CJK.search(after)):
        return "commentLang", ("ja" if RX_CJK.search(after) else "en")
    if RX_IMPORT.search(before):
        # import は、パス（モジュール）が変わった時だけ「書き方」。名前の追加・削除は中身の変更＝その他
        sb = "\0".join(t for t in tb if RX_STRTOK.match(t)); sa = "\0".join(t for t in ta if RX_STRTOK.match(t))
        if sb or sa:
            return ("import" if sb != sa else "other"), ""
        return ("import" if import_module(before) != import_module(after) else "other"), ""
    if tb and len(tb) == len(ta):
        diff = [i for i in range(len(tb)) if tb[i] != ta[i]]
        if len(diff) == 1 and RX_IDENT.match(tb[diff[0]]) and RX_IDENT.match(ta[diff[0]]):
            return "rename", f"{tb[diff[0]]} → {ta[diff[0]]}"
        if diff and all(RX_STRTOK.match(tb[i]) and RX_STRTOK.match(ta[i]) for i in diff):
            return "string", ""
        if diff and all(RX_NUMTOK.match(tb[i]) and RX_NUMTOK.match(ta[i]) for i in diff):
            return "number", ""
    return "other", ""

HABIT_STOP = set("const let var function return export import from default async await if else for while do switch case break continue new this class interface type enum extends implements public private protected static readonly void null undefined true false number string boolean any unknown never object in of as is try catch finally throw typeof instanceof yield def self None True False and or not elif pass lambda with print len str int float list dict set it test describe expect toBe toEqual fn func end then push length map filter get value key name id data result res err error e i j k n s t x y z max min optional describe z".split())

def tok_w(t):
    return 0.15 if (t in HABIT_STOP or len(t) <= 2 or RX_NUMTOK.match(t)) else 1.0

def tok_info(key):
    m = {}
    for t in tokens_of(key):
        m[t] = tok_w(t)
    return m, sum(m.values())

def sim_score(a, b):
    (ma, sa), (mb, sb) = a, b
    if not sa or not sb:
        return 0.0, False
    sh, content = 0.0, False
    for t, w in ma.items():
        if t in mb:
            sh += w
            if w == 1.0:
                content = True
    return 2 * sh / (sa + sb), content

def accept_in(s):
    return s[0] >= 0.5 or (s[1] and s[0] >= 0.3)

def accept_global(s):
    return s[0] >= 0.6 and s[1]

def analyze_habits(habit_in):
    """app.html の analyzeHabits と同じ：hunk（残っていない行の連なり）→ 窓の中で1対1 → 残りは削除／位置で組／まとまった削除"""
    H = {"lines": 0, "matched": 0, "items": []}
    agg = {}
    def add(hid, h, after, file, d):
        H["lines"] += 1
        if after is not None:
            H["matched"] += 1
        it = agg.setdefault(hid, {"id": hid, "count": 0, "sessions": set(), "files": set(), "examples": [], "dirs": {}})
        it["count"] += 1; it["sessions"].add(h["sid"] or ""); it["files"].add(file)
        if d:
            it["dirs"][d] = it["dirs"].get(d, 0) + 1
        if len(it["examples"]) < 8 and not RX_SECRET.search(h["key"]) and not (after and RX_SECRET.search(after)):
            it["examples"].append({"before": h["key"], "after": after, "file": file})
    for f in habit_in:
        m = RX_EXT.search(f["file"]); ext = (m.group(1) if m else "").lower()
        cur_list, pos = [], {}
        for k in f["cur"]:
            if k not in pos:
                pos[k] = len(cur_list); cur_list.append(k)
        info = {}
        def info_of(k):
            if k not in info:
                info[k] = tok_info(k)
            return info[k]
        used = set()
        def quick(h):
            return bool(RX_DEBUG.search(h["key"])) or is_comment_line(h["key"], ext)
        def resolve(lines, cands, anchored, comment_ok):
            scored = []
            for h in lines:
                for c in cands:
                    sc = sim_score(info_of(h["key"]), info_of(c))
                    if (accept_in(sc) if anchored else accept_global(sc)):
                        scored.append((sc[0], h["key"], c))
            scored.sort(key=lambda e: (-e[0], e[1], e[2]))
            pair, taken = {}, set()
            for _, hk, c in scored:
                if hk in pair or c in taken:
                    continue
                pair[hk] = c; taken.add(c)
            unp = [h for h in lines if h["key"] not in pair]
            rest_c = [c for c in cands if c not in taken]
            code_unp = [h for h in unp if not quick(h)]
            positional = anchored and 0 < len(code_unp) <= 3 and len(code_unp) == len(rest_c)
            block = (not positional) and len(unp) >= 3 and len(code_unp) >= 2
            if positional:
                for idx, h in enumerate(code_unp):
                    pair[h["key"]] = rest_c[idx]; taken.add(rest_c[idx])
            used.update(taken)
            all_comments = len(unp) > 0 and all(is_comment_line(h["key"], ext) for h in unp)
            for h in lines:
                after = pair.get(h["key"])
                if after is None and block:
                    add("block", h, None, f["file"], ""); continue
                hid, d = classify_pair(h["key"], after, ext)
                if hid == "comment" and not (comment_ok and all_comments):
                    add("delete", h, None, f["file"], ""); continue
                add(hid, h, after, f["file"], d)
        order = f["order"]; pending = []
        i = 0
        while i < len(order):
            if order[i]["alive"]:
                i += 1; continue
            start, seq = i, order[i]["seq"]
            j = i
            while j < len(order) and not order[j]["alive"] and order[j]["seq"] == seq:
                j += 1
            i = j
            lines = [o for o in order[start:j] if o["human"]]
            if not lines:
                continue
            prev_key = order[start - 1]["key"] if (start > 0 and order[start - 1]["seq"] == seq and order[start - 1]["alive"]) else None
            next_key = order[j]["key"] if (j < len(order) and order[j]["seq"] == seq and order[j]["alive"]) else None
            lo = pos[prev_key] if prev_key is not None else -1
            hi = pos[next_key] if next_key is not None else len(cur_list)
            if (prev_key is not None or next_key is not None) and hi > lo:
                cands = [k for k in cur_list[lo + 1:hi] if k not in f["claudeKeys"] and k not in used]
                comment_ok = prev_key is not None and next_key is not None and not is_comment_line(prev_key, ext) and not is_comment_line(next_key, ext)
                resolve(lines, cands, True, comment_ok)
            else:
                pending.append(lines)
        for lines in pending:
            resolve(lines, [k for k in cur_list if k not in f["claudeKeys"] and k not in used], False, False)
    for it in agg.values():
        dirs_sorted = sorted(it["dirs"].items(), key=lambda e: (-e[1], e[0]))
        d = dirs_sorted[0][0] if dirs_sorted else ""
        generic = it["id"] in HABIT_GENERIC
        candidate = (not generic) and it["count"] >= 3 and len(it["sessions"]) >= 2 and (it["id"] != "rename" or (bool(dirs_sorted) and dirs_sorted[0][1] >= 2))
        ex = []
        for e in it["examples"]:
            if len(ex) == 0 or (len(ex) == 1 and e["file"] != ex[0]["file"]):
                ex.append(e)
            if len(ex) == 2:
                break
        if len(ex) == 1 and len(it["examples"]) > 1:
            ex.append(it["examples"][1])
        H["items"].append({"id": it["id"], "label": HABIT_LABELS[it["id"]], "kind": HABIT_KIND.get(it["id"], "generic"), "count": it["count"], "sessions": len(it["sessions"]), "files": len(it["files"]),
                           "generic": generic, "candidate": candidate, "dir": d, "rule": None if generic else habit_rule(it["id"], d, it["count"]), "examples": ex})
    H["items"].sort(key=lambda a: (-int(a["candidate"]), int(a["generic"]), -a["count"], -a["sessions"], a["id"]))
    return H

def jround(x):
    return int(math.floor(x + 0.5))   # JS の Math.round と同じ（Python の round は偶数丸め）

def session_stats(per_sess, sess):
    """app.html の sessionStats と同じ：セッション全体の出力トークンを、このリポジトリの行の割合で按分"""
    rows = []
    out_total = 0; out_gone = 0
    for sid, ps in per_sess.items():
        if not ps["written"]:
            continue
        sv = sess.get(sid) or {"out": 0, "inp": 0, "cache": 0, "msgs": 0, "first": "", "start": None, "end": None, "bash": 0}
        share = ps["written"] / ps["writtenAll"] if ps["writtenAll"] else 0
        out_repo = jround(sv["out"] * share)
        gone = ps["written"] - ps["alive"]
        out_gone_repo = jround(out_repo * gone / ps["written"])
        out_total += out_repo; out_gone += out_gone_repo
        rows.append({"sid": sid, "first": sv["first"] or "", "start": date_key(sv["start"]) if sv["start"] is not None else "", "end": date_key(sv["end"]) if sv["end"] is not None else "",
                     "out": sv["out"], "outRepo": out_repo, "share": share, "msgs": sv["msgs"], "bash": sv["bash"], "members": sv.get("members", 1), "edits": ps["edits"],
                     "written": ps["written"], "alive": ps["alive"], "rewritten": ps["rewritten"], "human": ps["human"], "dropped": ps["dropped"],
                     "perAlive": jround(out_repo / ps["alive"]) if ps["alive"] else None})
    rows.sort(key=lambda r: (-r["outRepo"], -r["written"], r["sid"]))
    big = [r for r in rows if r["written"] >= 20 and r["outRepo"] > 0]
    costly = sorted([r for r in big if r["perAlive"] is None or r["alive"] / r["written"] < 0.7], key=lambda r: (0 if r["perAlive"] is None else 1, -(r["outRepo"] if r["perAlive"] is None else r["perAlive"]), r["sid"]))[:3]
    cheap = sorted([r for r in big if r["perAlive"] is not None and r["alive"] / r["written"] >= 0.7], key=lambda r: (r["perAlive"], r["sid"]))[:3]
    return {"outTotal": out_total, "outGone": out_gone, "goneShare": (out_gone / out_total) if out_total else 0, "rows": rows,
            "costly": [r["sid"] for r in costly], "cheap": [r["sid"] for r in cheap]}

def analyze(acc, project, project_name, strict):
    evs = build_events(acc)
    claude, applied = apply_events(evs, acc, strict)
    cwds = {}
    for a in applied:
        if a["cwd"]:
            cwds[a["cwd"]] = cwds.get(a["cwd"], 0) + 1
    cwd_top = (sorted(cwds.items(), key=lambda e: (-e[1], e[0])) or [("", 0)])[0][0]
    root, matched, candidates, ambiguous, src = find_root(claude, project, cwds, project_name)
    R = {"sample": False, "strict": bool(strict), "projectName": project_name or "", "root": root or "", "rootFrom": src, "rootAmbiguous": ambiguous, "cwdTop": cwd_top,
         "logFiles": acc["files"], "logLines": acc["lines"], "logBad": acc["bad"], "uses": len(acc["uses"]), "edits": 0, "sessions": 0,
         "projectFiles": len(project), "projectLines": 0, "otherProjectFiles": 0, "missingFiles": [],
         "written": 0, "alive": 0, "rewritten": 0, "human": 0, "dropped": 0, "droppedWritten": 0, "aiLines": 0,
         "period": None, "files": [], "top": [], "examples": {"alive": None, "human": None}, "rootCandidates": candidates, "rootMatched": matched,
         "habits": {"lines": 0, "matched": 0, "items": []},
         "sessionStats": {"outTotal": 0, "outGone": 0, "goneShare": 0, "rows": [], "costly": [], "cheap": []}}
    if not root:
        return R
    prefix = root + "/"
    sids = set(); tmin = None; tmax = None
    per_sess = {}
    rep_of, sess_merged = resolve_sessions(acc)
    def rep_sid(sid):
        return rep_of.get(sid, sid)
    def ps_of(sid):
        sid = rep_sid(sid)
        v = per_sess.get(sid)
        if v is None:
            v = {"written": 0, "alive": 0, "rewritten": 0, "human": 0, "dropped": 0, "edits": 0, "writtenAll": 0}; per_sess[sid] = v
        return v
    for a in applied:
        if not a["path"].startswith(prefix):
            continue
        R["edits"] += 1; sids.add(rep_sid(a["sid"])); ps_of(a["sid"])["edits"] += 1
        tmin = a["ts"] if tmin is None or a["ts"] < tmin else tmin
        tmax = a["ts"] if tmax is None or a["ts"] > tmax else tmax
    R["sessions"] = len(sids)
    if R["edits"]:
        s, e = date_key(tmin), date_key(tmax)
        R["period"] = {"start": s, "end": e, "days": days_between(s, e) + 1}
    alive_c, human_c = [], []
    habit_in = []   # 直し癖の材料（app.html の habitIn と同じ）
    seen_rel = set()
    for p, m in claude.items():
        if not p.startswith(prefix):
            R["otherProjectFiles"] += 1
            continue
        rel = p[len(prefix):]
        seen_rel.add(rel)
        text = project.get(rel)
        # 行は「種類」で数える（同じ内容の行は1つ）＝app.html と同じ
        cur_set = set() if text is None else set(line_keys(text, strict))
        row = {"file": rel, "exists": text is not None, "lines": len(cur_set), "written": len(m), "alive": 0, "rewritten": 0, "human": 0, "ai": 0}
        human_n = 0
        for k, rec in m.items():
            ps = ps_of(rec.get("sid", "")); ps["written"] += 1
            if k in cur_set:
                row["alive"] += 1; alive_c.append({"key": k, "file": rel}); ps["alive"] += 1
            elif rec["removed"]:
                row["rewritten"] += 1; ps["rewritten"] += 1
            else:
                row["human"] += 1
                if text is not None:   # 典型的な「人が消した行」は、今もあるファイルから
                    human_c.append({"key": k, "file": rel}); human_n += 1; ps["human"] += 1
                else:
                    ps["dropped"] += 1
        if human_n:
            habit_in.append({"file": rel, "claudeKeys": m,
                             "order": [{"key": k, "seq": rec["seq"], "sid": rep_sid(rec.get("sid", "")), "alive": k in cur_set, "human": (k not in cur_set) and not rec["removed"]} for k, rec in m.items()],
                             "cur": line_keys(text, strict)})
        row["ai"] = row["alive"]
        for k in ("written", "alive", "rewritten", "human"):
            R[k] += row[k]
        R["aiLines"] += row["ai"]
        if text is None:
            # ファイルごと消えた：中の「人が消した」行は dropped に分けて数える
            R["dropped"] += row["human"]; R["droppedWritten"] += row["written"]
            R["missingFiles"].append({"file": rel, "exists": False, "written": row["written"], "rewritten": row["rewritten"], "human": row["human"]})
        else:
            R["files"].append(row)
    for rel, text in project.items():
        n = len(set(line_keys(text, strict)))
        R["projectLines"] += n
        if rel not in seen_rel:
            R["files"].append({"file": rel, "exists": True, "lines": n, "written": 0, "alive": 0, "rewritten": 0, "human": 0, "ai": 0})
    R["files"].sort(key=lambda f: (-f["written"], -f["lines"], f["file"]))
    R["missingFiles"].sort(key=lambda f: (-f["written"], f["file"]))
    assign_aliases(R)
    # 急所＝今もあるファイルだけ（ファイルごと消えたものは dropped に分けた）
    top = [f for f in R["files"] if f["human"] > 0]
    top.sort(key=lambda f: (-f["human"], -f["written"], f["file"]))
    R["top"] = [{"file": f["file"], "alias": f["alias"], "human": f["human"], "written": f["written"], "exists": True} for f in top[:3]]
    R["examples"] = {"alive": pick_example(alive_c), "human": pick_example(human_c)}
    R["habits"] = analyze_habits(habit_in)
    for m in claude.values():
        for rec in m.values():
            ps = per_sess.get(rep_sid(rec.get("sid", "")))
            if ps:
                ps["writtenAll"] += 1
    R["sessionStats"] = session_stats(per_sess, sess_merged)
    return R

# ---------- プロジェクトのフォルダ（app.html と同じ除外） ----------
PROJ_SKIP_DIRS = {"node_modules", ".git", ".hg", ".svn", "dist", "build", "out", ".next", ".nuxt", ".output", ".svelte-kit", ".turbo", ".cache", "coverage", "vendor", "__pycache__", ".venv", "venv", "target", "Pods", "DerivedData", ".idea", ".vscode", ".claude", ".pytest_cache", ".mypy_cache", ".parcel-cache", ".gradle", "bin", "obj"}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "Cargo.lock", "poetry.lock", "Pipfile.lock", "Gemfile.lock", "composer.lock", "go.sum", ".DS_Store", "Thumbs.db"}
BIN_EXT = re.compile(r"\.(png|jpe?g|gif|webp|avif|ico|icns|bmp|tiff?|psd|svg|woff2?|ttf|otf|eot|mp[34]|m4a|wav|ogg|webm|mov|avi|zip|gz|tgz|bz2|xz|7z|rar|jar|war|pdf|wasm|exe|dll|so|dylib|class|pyc|pyo|o|a|lib|bin|dat|db|sqlite3?|lock|map|min\.js|min\.css|ipynb|pb|onnx|safetensors|ckpt|pt|npy|npz|parquet|keynote|numbers|pages|docx?|xlsx?|pptx?)$", re.I)
MAX_TEXT = int(1.5 * 1024 * 1024)

def project_filter(rel, size):
    segs = rel.split("/")
    name = segs[-1]
    if any(s in PROJ_SKIP_DIRS for s in segs[:-1]):
        return False
    if name in SKIP_FILES or BIN_EXT.search(name):
        return False
    if size > MAX_TEXT:
        return False
    return True

def load_project(project_dir):
    project_dir = pathlib.Path(project_dir)
    project = {}
    for p in sorted(project_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(project_dir).as_posix()
        if not project_filter(rel, p.stat().st_size):
            continue
        text = p.read_bytes().decode("utf-8", errors="replace")
        if text.startswith("﻿"):
            text = text[1:]
        if "\x00" in text[:4096]:
            continue
        project[rel] = text
    return project

def run_texts(log_texts, project, project_name, strict=False):
    """文字列から同じ計算（app.html の analyzeTexts と対）。log_texts: [str]、project: {rel: text}"""
    acc = new_acc()
    for text in log_texts:
        parts = text.split("\n")
        if parts and parts[-1] == "":
            parts.pop()
        for line in parts:
            handle_line(line, acc)
        acc["files"] += 1
    pm = {}
    for rel, text in project.items():
        if project_filter(rel, utf16len(text)) and "\x00" not in text[:4096]:
            pm[norm_path(rel)] = text
    return analyze(acc, pm, project_name or "", strict)

def run(log_paths, project_dir, strict=False):
    acc = new_acc()
    for p in log_paths:
        p = pathlib.Path(p)
        if p.suffix.lower() != ".jsonl" or any(seg in LOG_SKIP_DIRS for seg in p.parts):
            continue
        read_log_file(p, acc)
    project = load_project(project_dir)
    return analyze(acc, project, pathlib.Path(project_dir).name, strict)

if __name__ == "__main__":
    import sys
    logs = [p for p in pathlib.Path(sys.argv[1]).rglob("*.jsonl")]
    print(json.dumps(run(logs, sys.argv[2], strict="--strict" in sys.argv), ensure_ascii=False, indent=1))
