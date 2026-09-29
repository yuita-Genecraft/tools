#!/usr/bin/env python3
"""通知表の集計を Python で別に実装した参照版。JS の結果と突き合わせる。"""
import json, re, sys, pathlib, datetime
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tokyo")
PRICES = [
    ('claude-fable-5-1', 10, 12.5, 20, 0.25, 50), ('claude-mythos-5-1', 10, 12.5, 20, 0.25, 50),
    ('claude-fable-5', 10, 12.5, 20, 1, 50), ('claude-mythos-5', 10, 12.5, 20, 1, 50),
    ('claude-opus-5-5', 4, 5, 8, 0.2, 20), ('claude-opus-5', 5, 6.25, 10, 0.5, 25),
    ('claude-opus-4-8', 5, 6.25, 10, 0.5, 25), ('claude-opus-4-7', 5, 6.25, 10, 0.5, 25),
    ('claude-opus-4-6', 5, 6.25, 10, 0.5, 25), ('claude-opus-4-5', 5, 6.25, 10, 0.5, 25),
    ('claude-opus-4-1', 15, 18.75, 30, 1.5, 75), ('claude-opus-4', 15, 18.75, 30, 1.5, 75),
    ('claude-sonnet-5-5', 2, 2.5, 4, 0.2, 10), ('claude-sonnet-5', 2, 2.5, 4, 0.2, 10),
    ('claude-sonnet-4-6', 3, 3.75, 6, 0.3, 15), ('claude-sonnet-4-5', 3, 3.75, 6, 0.3, 15),
    ('claude-sonnet-4', 3, 3.75, 6, 0.3, 15), ('claude-haiku-4-5', 1, 1.25, 2, 0.1, 5),
    ('claude-haiku-3-5', 0.8, 1, 1.6, 0.08, 4), ('claude-3-7-sonnet', 3, 3.75, 6, 0.3, 15),
    ('claude-3-5-sonnet', 3, 3.75, 6, 0.3, 15), ('claude-3-5-haiku', 0.8, 1, 1.6, 0.08, 4),
    ('claude-3-opus', 15, 18.75, 30, 1.5, 75), ('claude-3-haiku', 0.25, 0.3, 0.5, 0.03, 1.25),
]
FAM = [('fable', 'claude-fable-5-1'), ('mythos', 'claude-mythos-5-1'), ('opus', 'claude-opus-5-5'), ('sonnet', 'claude-sonnet-5-5'), ('haiku', 'claude-haiku-4-5')]

def price(model):
    m = model.lower()
    best = None
    for p in PRICES:
        if m.startswith(p[0]) and (best is None or len(p[0]) > len(best[0])):
            best = p
    if best:
        return best, False
    for fam, pid in FAM:
        if fam in m:
            return next(p for p in PRICES if p[0] == pid), True
    return None, True

RX = dict(
    ossha=re.compile(r"おっしゃる(通り|とおり)|仰る(通り|とおり)|ご指摘の(通り|とおり)|you['’]re (absolutely |completely |totally )?(right|correct)", re.I),
    shazai=re.compile(r"申し訳(ありません|ございません|ない|なかった)|すみません|失礼(しました|いたしました)|お詫び|I apologi[sz]e|my apologies|sorry (about|for)", re.I),
    kanpeki=re.compile(r"完璧(です|でした|に|な|！|!|。)|perfect[!.]", re.I),
    shouchi=re.compile(r"承知(しました|いたしました)|かしこまりました|了解(しました|です)"),
)
YRX = dict(
    chigau=re.compile(r"違う|ちがう|違います|ちがいます|違くて|そうじゃな|そうではな|そういうことじゃな"),
    arigato=re.compile(r"ありがと|有難う|有り難う|助かった|助かります|助かる|感謝|thanks|thank you|\bthx\b", re.I),
    naze=re.compile(r"なんで|なぜ|何故|どうして"),
    modoshite=re.compile(r"戻して|元に戻|もとに戻|もどして|revert|ロールバック|取り消して|やり直し|やりなおし", re.I),
    ultrathink=re.compile(r"ultrathink|think harder|think hard|megathink", re.I),
    yoshinani=re.compile(r"よしなに|いい感じに|いいかんじに|良い感じに|よい感じに|うまいこと|うまく(やって|して)"),
    error=re.compile(r"error|エラー|exception|traceback|failed|失敗", re.I),
    ugokanai=re.compile(r"動かない|動きません|うごかない|直らない|治らない|直ってない|治ってない|変わってない|変わらない"),
    onegai=re.compile(r"お願い|おねがい|please|ください|下さい", re.I),
)
POLITE = re.compile(r"です|ます|ください|下さい|お願い|でしょうか")
LIMIT = re.compile(r"limit reached|usage limit|hit your limit|rate limit|上限", re.I)
APIERR = re.compile(r"API Error|overloaded|Prompt is too long", re.I)
COMPACT = "This session is being continued from a previous conversation"
TSUZUKE = re.compile(r"^(続けて|つづけて|続き|続行|進めて|すすめて|continue|go on|go ahead|keep going)(ください|下さい|お願い(します)?)?[。．.!！\s]*$", re.I)
WRAP = re.compile(r"^<(command-name|command-message|command-args|local-command-stdout|local-command-stderr|bash-input|bash-stdout|bash-stderr|system-reminder|user-memory-input)>")

def run(paths):
    seen = set(); req = {}; sess = defaultdict(lambda: dict(h=[], a=[]))
    S = dict(prompts=0, interrupts=0, rejects=0, images=0, lines=0, bad=0, compacts=0, limitHits=0, apiErrors=0, polite=0)
    you = Counter(); cl = Counter(); tools = Counter(); days = defaultdict(lambda: [0, 0]); hours = [0] * 24
    for path in paths:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        parts = content.split("\n")
        if parts and parts[-1] == "":
            parts = parts[:-1]
        for line in parts:
            S["lines"] += 1
            if len(line) < 30:
                continue
            if '"type":"assistant"' not in line and '"type":"user"' not in line and '"type": "assistant"' not in line and '"type": "user"' not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                S["bad"] += 1
                continue
            if not isinstance(o, dict) or o.get("type") not in ("user", "assistant"):
                continue
            u = o.get("uuid")
            if isinstance(u, str):
                if u in seen:
                    continue
                seen.add(u)
            m = o.get("message") or {}
            ts = o.get("timestamp")
            tsv = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000 if isinstance(ts, str) and ts else None
            sid = o.get("sessionId") if isinstance(o.get("sessionId"), str) else str(path)
            if o["type"] == "assistant":
                model = m.get("model") or ""
                synthetic = model == "<synthetic>" or o.get("isApiErrorMessage") is True
                if tsv is not None and not synthetic:
                    sess[sid]["a"].append(tsv)
                if synthetic:
                    cont = m.get("content")
                    tx = " ".join((b.get("text") if isinstance(b, dict) and isinstance(b.get("text"), str) else "") for b in cont) if isinstance(cont, list) else (cont if isinstance(cont, str) else "")
                    if LIMIT.search(tx):
                        S["limitHits"] += 1
                    elif o.get("isApiErrorMessage") is True or APIERR.search(tx):
                        S["apiErrors"] += 1
                us = m.get("usage")
                if isinstance(us, dict) and model and model != "<synthetic>":
                    key = f"{m.get('id') or ''}|{o.get('requestId') or ''}"
                    if key == "|":
                        key = "line:" + str(u)
                    cc = us.get("cache_creation") if isinstance(us.get("cache_creation"), dict) else None
                    cw = us.get("cache_creation_input_tokens") or 0
                    if cc and (cc.get("ephemeral_5m_input_tokens") or 0) + (cc.get("ephemeral_1h_input_tokens") or 0) > 0:
                        c5, c1 = cc.get("ephemeral_5m_input_tokens") or 0, cc.get("ephemeral_1h_input_tokens") or 0
                    else:
                        c5, c1 = cw, 0
                    rec = dict(model=model, i=us.get("input_tokens") or 0, c5=c5, c1=c1, cr=us.get("cache_read_input_tokens") or 0, o=us.get("output_tokens") or 0)
                    if key not in req:
                        req[key] = rec
                    else:
                        for k in ("i", "c5", "c1", "cr", "o"):
                            req[key][k] = max(req[key][k], rec[k])
                for b in (m.get("content") or []) if isinstance(m.get("content"), list) else []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        tools[b.get("name") or "unknown"] += 1
                    elif b.get("type") == "text" and o.get("isSidechain") is not True and isinstance(b.get("text"), str):
                        for k, rx in RX.items():
                            if rx.search(b["text"]):
                                cl[k] += 1
                continue
            c = m.get("content")
            text, has, imgs, had_result = "", False, 0, False
            if isinstance(c, str):
                text, has = c, True
            elif isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result":
                        had_result = True
                        rc = b.get("content")
                        rt = rc if isinstance(rc, str) else "".join(x.get("text", "") for x in rc if isinstance(x, dict)) if isinstance(rc, list) else ""
                        if "doesn't want to proceed with this tool use" in rt:
                            S["rejects"] += 1
                    elif b.get("type") == "text" and isinstance(b.get("text"), str):
                        text += ("\n" if has else "") + b["text"]
                        has = True
                    elif b.get("type") == "image":
                        imgs += 1
            if had_result and tsv is not None:
                sess[sid]["a"].append(tsv)
            if not has and not imgs:
                continue
            if o.get("isSidechain") is not True and (o.get("isCompactSummary") is True or text.lstrip().startswith(COMPACT)):
                S["compacts"] += 1
                continue
            if o.get("isSidechain") is True or o.get("isMeta") is True or o.get("isCompactSummary") is True:
                continue
            if isinstance(o.get("userType"), str) and o["userType"] != "external":
                continue
            s = text.lstrip()
            if s.startswith("[Request interrupted by user"):
                S["interrupts"] += 1
                continue
            if WRAP.match(s) or s.startswith("Caveat: The messages below"):
                continue
            S["prompts"] += 1
            S["images"] += imgs
            for k, rx in YRX.items():
                if rx.search(text):
                    you[k] += 1
            if TSUZUKE.match(text.strip()):
                you["tsuzukete"] += 1
            if POLITE.search(text):
                S["polite"] += 1
            if isinstance(ts, str) and ts:
                sess[sid]["h"].append(tsv)
                d = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ)
                hours[d.hour] += 1
                dk = d.strftime("%Y-%m-%d")
                days[dk][0] += 1
                if d.hour < 5:
                    days[dk][1] += 1
    models = defaultdict(lambda: dict(calls=0, i=0, c5=0, c1=0, cr=0, o=0))
    for r in req.values():
        b = models[r["model"]]
        b["calls"] += 1
        for k in ("i", "c5", "c1", "cr", "o"):
            b[k] += r[k]
    usd = 0.0; tokens = 0; per = {}
    for mname, b in models.items():
        p, est = price(mname)
        cost = (b["i"] * p[1] + b["c5"] * p[2] + b["c1"] * p[3] + b["cr"] * p[4] + b["o"] * p[5]) / 1e6 if p else 0
        per[mname] = dict(b, usd=cost, estimated=est)
        usd += cost
        tokens += b["i"] + b["c5"] + b["c1"] + b["cr"] + b["o"]
    work = 0.0
    for b in sess.values():
        if not b["h"] or not b["a"]:
            continue
        H = sorted(b["h"]); A_ = sorted(b["a"])
        for i, st_ in enumerate(H):
            end = H[i + 1] if i + 1 < len(H) else float("inf")
            cand = [x for x in A_ if x < end]
            if cand and cand[-1] > st_:
                work += min(cand[-1] - st_, 2 * 3600 * 1000)
    keys = sorted(days)
    streak = run_ = 0
    prev = None
    for k in keys:
        dk = datetime.date.fromisoformat(k)
        run_ = run_ + 1 if prev and (dk - prev).days == 1 else 1
        streak = max(streak, run_)
        prev = dk
    return dict(S, workMin=work / 60000, politeRatio=(S["polite"] / S["prompts"]) if S["prompts"] else 0, you=dict(you), claude=dict(cl), tools=dict(tools), usd=usd, tokens=tokens, models=per,
                activeDays=len(keys), nightDays=sum(1 for v in days.values() if v[1] > 0), streak=streak,
                nightPrompts=sum(hours[:5]), period=(keys[0], keys[-1]) if keys else None)

if __name__ == "__main__":
    ps = []
    for a in sys.argv[1:]:
        p = pathlib.Path(a)
        ps += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    print(json.dumps(run(ps), ensure_ascii=False, indent=1, default=str))
