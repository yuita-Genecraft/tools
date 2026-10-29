// engine.js の部品を直接たたく（.gitignore の読み・ルールの読み）
import fs from "node:fs"; import vm from "node:vm";
const src = fs.readFileSync(new URL("../fbcheck-web/engine.js", import.meta.url), "utf8");
const ctx = {}; vm.createContext(ctx); vm.runInContext(src + "\n;globalThis.E={gitignoreCovers, matchChains, allowsIn, isWholeScope, globToRegex, runChecks, looseJson};", ctx);
const { gitignoreCovers, matchChains, allowsIn, isWholeScope, runChecks, looseJson } = ctx.E;
let fail = 0;
const t = (name, got, want) => { const ok = JSON.stringify(got) === JSON.stringify(want); if (!ok) fail++; console.log((ok ? "OK  " : "NG  ") + name + (ok ? "" : `  got=${JSON.stringify(got)} want=${JSON.stringify(want)}`)); };
const C = (gi, rel) => gitignoreCovers(gi, rel).covered;
t(".env が .env を除外", C(".env", ".env"), true);
t(".env は .env.production を除外しない", C(".env", ".env.production"), false);
t(".env* が .env.production を除外", C(".env*", ".env.production"), true);
t("*.local が .env.local を除外", C("*.local", ".env.local"), true);
t(".env*.local が .env.production.local を除外", C(".env*.local", ".env.production.local"), true);
t(".env*.local は .env.production を除外しない", C(".env*.local", ".env.production"), false);
t("/.env は下の階層を除外しない", C("/.env", "apps/web/.env"), false);
t("/.env は直下を除外", C("/.env", ".env"), true);
t(".env（斜線なし）はどの階層でも除外", C(".env", "apps/web/.env"), true);
t("apps/web/.env はそのパスを除外", C("apps/web/.env", "apps/web/.env"), true);
t("web/.env（途中に斜線）は直下からの相対", C("web/.env", "apps/web/.env"), false);
t("**/.env は下の階層を除外", C("**/.env", "apps/web/.env"), true);
t("**/.env は直下も除外", C("**/.env", ".env"), true);
t("apps/ はその中を除外", C("apps/", "apps/web/.env"), true);
t(".env/ はファイル .env を除外しない", C(".env/", ".env"), false);
t("! で打ち消すと除外と言わない", C(".env\n!.env", ".env"), false);
t(".env* のあと !.env.production", C(".env*\n!.env.production", ".env.production"), false);
t(".env* のあと !.env.example は .env.local に影響しない", C(".env*\n!.env.example", ".env.local"), true);
t("[ ] の書き方は読めないので言い切らない", C("[.]env", ".env"), false);
t("コメントは無視", C("# .env", ".env"), false);
t("末尾の空白は無視", C(".env  ", ".env"), true);
t("* はすべて除外", C("*", ".env"), true);
t(".gitignore なし", C(null, ".env"), false);
t("CRLF", C("node_modules\r\n.env*\r\n", ".env.local"), true);
// ルールの読み
const rules = `rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read: if request.auth != null; // コメント { }
      match /posts/{postId} { allow write: if true; }
    }
    match /{document=**} { allow read, write: if request.auth != null; }
  }
}`;
const ch = matchChains(rules);
t("入れ子の match（4行目の中）", ch[4], ["/databases/{database}/documents", "/users/{userId}"]);
t("1行に match と allow", ch[5], ["/databases/{database}/documents", "/users/{userId}", "/posts/{postId}"]);
t("閉じた後の {document=**}", ch[7], ["/databases/{database}/documents", "/{document=**}"]);
t("{document=**} は全体", isWholeScope(ch[7]), true);
t("/users/{userId} は全体ではない", isWholeScope(ch[4]), false);
t("一続きのパスでも全体", isWholeScope(["/databases/{database}/documents/{document=**}"]), true);
t("Storage の全体", isWholeScope(["/b/{bucket}/o", "/{allPaths=**}"]), true);
t("allow の取り出し", allowsIn("allow read, write: if request.auth != null;").map(a => [a.ops, a.cond]), [[["read", "write"], "request.auth != null"]]);
t("1行に2つの allow", allowsIn("allow read: if true; allow write: if false;").map(a => a.cond), ["true", "false"]);
t("&& つきは auth だけではない", allowsIn("allow read: if request.auth != null && request.auth.uid == userId;")[0].cond, "request.auth != null && request.auth.uid == userId");
// 文言：期限切れの説明と apiKey の助言
const P = { files: [{ rel: "firestore.rules", name: "firestore.rules" }, { rel: "src/fb.ts", name: "fb.ts" }],
  texts: new Map([["firestore.rules", "service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      allow read, write: if request.time < timestamp.date(2020, 1, 1);\n    }\n  }\n}\n"],
                  ["src/fb.ts", 'const c = { apiKey: "AIzaSyEXAMPLEexampleEXAMPLE0" };\n']]), gitignore: null };
const R = runChecks(P);
const exp = R.findings.warn.find((f) => f.title.startsWith("期限切れの無認証許可ルール"));
t("期限切れ：別の allow が true なら許可と書く", !!exp && exp.why.includes("別の allow が true なら、アクセスは許可されます"), true);
t("期限切れ：「拒否されているはず」と断定しない", !!exp && !exp.why.includes("拒否されているはず"), true);
const info = R.findings.info[0];
t("apiKey：API の制限（Firebase 関連だけ）を主に案内", !!info && info.how.includes("「API の制限」が Firebase 関連の API だけ") && info.how.includes("別のキー"), true);
t("apiKey：HTTP リファラ単独の助言はしない", !!info && !info.how.includes("HTTP リファラ"), true);
// 公式：2024年5月の自動制限は「新しく自動で作られたキー」だけ。それより前のキーは、当時有効だった別の API も許可に残りうる
t("apiKey：自動制限は2024年5月以降に作られたキーだけと書く", !!info && info.how.includes("2024年5月以降に Firebase が自動で作ったキー") && info.how.includes("それより前に作られたキーは、Firebase 以外の API も許可に入っていることがあります"), true);
const P2 = { files: [{ rel: ".env", name: ".env" }], texts: new Map([[".env", "X=1\n"]]), gitignore: ".env*\n" };
t("envStatus なし（ブラウザ版）＝除外済みと言わず未確認", runChecks(P2).findings.warn.map((f) => f.title), [".env が Git で追跡済みかは、ここでは確かめられません"]);
t("envStatus=untracked_ignored（git で確認済み）＝何も出さない", runChecks({ ...P2, envStatus: new Map([[".env", "untracked_ignored"]]) }).findings.warn.length, 0);
t("envStatus=tracked＝危険", runChecks({ ...P2, envStatus: new Map([[".env", "tracked"]]) }).findings.danger.map((f) => f.title), ["Git で追跡されている .env ファイルがあります"]);

// ---- 判定の直し（fbcheck-review v0.1：P0-1・P0-2・P1-1・P1-2）
const FS = (body) => `rules_version = '2';\nservice cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      ${body}\n    }\n  }\n}\n`;
const ST = (body) => `rules_version = '2';\nservice firebase.storage {\n  match /b/{bucket}/o {\n    match /{allPaths=**} {\n      ${body}\n    }\n  }\n}\n`;
const PKG = '{"name":"x","dependencies":{"firebase":"^11.0.0"}}';
const mk = (files, extra = {}) => ({ files: Object.keys(files).map((rel) => ({ rel, name: rel.split("/").pop() })), texts: new Map(Object.entries(files)), gitignore: null, ...extra });
const run = (files, extra) => runChecks(mk({ "package.json": PKG, ...files }, extra)).findings;
const titles = (F, k) => F[k].map((f) => f.title);
const UNRES = (f) => f.title.startsWith("判定できなかった allow の行があります");
// B1：条件なしの allow（P0-1）
t("B1：allow read, write;（条件なし）＝danger 誰でも読み書き", titles(run({ "firestore.rules": FS("allow read, write;") }), "danger"), ["誰でも読み書きできる状態です（firestore.rules）"]);
{
  const F = run({ "storage.rules": ST("allow read;\n      allow write: if request.auth != null;") });
  t("B1：Storage 全体の allow read; ＋ write の auth＝danger 2件（読める・書き込める）", titles(F, "danger"), ["誰でも読める状態です（storage.rules）", "ログインすれば、すべてのファイルを書き込めます（storage.rules）"]);
}
t("B1：1行に書いた allow read, write; も拾う", allowsIn("allow read, write;").map((a) => [a.ops, a.cond, !!a.bare]), [[["read", "write"], "true", true]]);
t("B1：allow read; allow write: if false; の2つ", allowsIn("allow read; allow write: if false;").map((a) => a.cond), ["true", "false"]);
t("B1：一部の場所の allow get; は warn（読み取りだけ）", titles(run({ "firestore.rules": "service cloud.firestore {\n  match /databases/{database}/documents {\n    match /posts/{id} {\n      allow get;\n    }\n  }\n}\n" }), "warn"), ["誰でも読める場所があります（firestore.rules）"]);
// B2：判定できなかった allow の行（P0-2）
const unresolvedOf = (body) => run({ "firestore.rules": FS(body) }).warn.filter(UNRES);
for (const [name, body, lineNo] of [
  ["#03 || true", "allow read, write: if request.auth != null || true;", 5], ["#04 条件が次の行（auth）", "allow read, write: if\n        request.auth != null;", 5],
  ["#05 条件が次の行（true）", "allow read, write: if\n        true;", 5], ["#06 括弧", "allow read, write: if (request.auth != null);", 5],
  ["#15 関数", "allow read, write: if isSignedIn();", 5], ["ops が複数行", "allow read,\n        write: if true;", 5],
]) {
  const u = unresolvedOf(body);
  t(`B2/N2：${name}＝無言にしない（行の実物つき）`, [u.length, u[0] && u[0].evidence[0].loc, u[0] && u[0].evidence[0].code.startsWith("allow")], [1, `firestore.rules:${lineNo}`, true]);
}
t("B2：件数が見出しに出る", unresolvedOf("allow read: if f(1);\n      allow write: if g(2);")[0].title, "判定できなかった allow の行があります（2 行・firestore.rules）");
t("B2：持ち主の照合（&&・uid ==）・false は無言（言い過ぎを増やさない）", ["allow read, write: if request.auth != null && request.auth.uid == userId;", "allow read: if request.auth.uid == userId;", "allow write: if false;", "allow read: if resource.data.owner == request.auth.uid;"].map((b) => unresolvedOf(b).length), [0, 0, 0, 0]);
t("B2：コメントの中の「allow」という語では出さない", unresolvedOf("/* allow only the owner */\n      // allow nothing here\n      allow write: if false;").length, 0);
// B3：request.auth.uid != null
t("B3：request.auth.uid != null が全体＝danger（ログインすれば…）", titles(run({ "firestore.rules": FS("allow read, write: if request.auth.uid != null;") }), "danger"), ["ログインすれば、すべての文書を読み書きできます（firestore.rules）"]);
// B4：Gemini のキー（P1-1）
const AK = ["AIza", "SyFAKEFAKEFAKEFAKEFAKE_12345-abc"].join("");
const geminiTitles = (F) => F.danger.filter((f) => f.title.startsWith("Gemini のキー")).map((f) => f.title);
t("B4：@google/genai ＋ ソースに AIza＝danger", geminiTitles(run({ "src/ai.ts": `import { GoogleGenAI } from "@google/genai";\nconst ai = new GoogleGenAI({ apiKey: "${AK}" });\n` })), ["Gemini のキーがブラウザ側に出ています"]);
t("B4：VITE_GEMINI_API_KEY=AIza…（.env）が素通りしない", geminiTitles(run({ "package.json": '{"dependencies":{"@google/generative-ai":"^0.21.0"}}', ".env": `VITE_GEMINI_API_KEY=${AK}\n` }, { envStatus: new Map([[".env", "untracked_ignored"]]) })), ["Gemini のキーがブラウザ側に出ています"]);
t("B4：配布物（dist）の AIza も拾う", geminiTitles(run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "dist/assets/a.js": `var c="generativelanguage.googleapis.com";var k="${AK}";\n` })), ["Gemini のキーがブラウザ側に出ています"]);
t("B4：痕跡が1つも無い apiKey: AIza…＝danger にしない（N3）", geminiTitles(run({ "src/fb.ts": `const c = { apiKey: "${AK}" };\n` })), []);
t("B4：Gemini の痕跡があっても firebaseConfig の apiKey は Gemini と言わない", geminiTitles(run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "src/fb.ts": `const firebaseConfig = {\n  apiKey: "${AK}",\n  authDomain: "d.firebaseapp.com",\n  storageBucket: "d.appspot.com",\n};\n` })), []);
t("B4：サーバー側の .env（接頭辞なし）の GEMINI_API_KEY は Gemini の danger にしない", geminiTitles(run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', ".env": `GEMINI_API_KEY=${AK}\n` }, { envStatus: new Map([[".env", "untracked_ignored"]]) })), []);
{
  const F = run({ "src/fb.ts": `const c = { apiKey: "${AK}", authDomain: "d.firebaseapp.com" };\n` });
  t("B4：痕跡なし＝従来の info のまま＋Gemini の1行", [F.info.length, F.info[0].title, F.info[0].how.includes("Gemini Developer API のキーは Firebase のキーとは別物")], [1, "Firebase の apiKey がフロントに出ているのは、正常です", true]);
  const F2 = run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "src/ai.ts": `new GoogleGenAI({ apiKey: "${AK}" });\n` });
  t("B4：Gemini の鍵の行を「Firebase の apiKey は正常」と言わない", F2.info.length, 0);
}
// B5：Realtime Database の rules（P1-2）
const rt = (text) => run({ "database.rules.json": text });
const COMMENTED = '{\n  "rules": {\n    // このルールは 2023-3-25 まで\n    ".read": "now < 1679680800000",  // 2023-3-25\n    ".write": "now < 1679680800000",  /* 同じ */\n  }\n}\n';
t("B5：コメント入り・末尾カンマの JSON を読める（期限切れ＝warn）", titles(rt(COMMENTED), "warn"), ["期限切れの無認証許可ルールがあります（Firebase のテストモードと同じ形・Realtime Database・database.rules.json）"]);
t("B5：now < 期限内＝danger", titles(rt('{"rules":{".read":"now < 4102444800000",".write":false}}'), "danger"), ["期限まで無認証で許可するルールがあります（Firebase のテストモードと同じ形・Realtime Database・database.rules.json）"]);
t("B5：top の auth != null（firebase init の既定）＝danger", titles(rt('{"rules":{".read":"auth != null",".write":"auth != null"}}'), "danger"), ["ログインすれば、Realtime Database 全体を読み書きできます（database.rules.json）"]);
t("B5：auth !== null も同じ", titles(rt('{"rules":{".read":"auth !== null"}}'), "danger"), ["ログインすれば、Realtime Database 全体を読めます（database.rules.json）"]);
t("B5：一部の場所の auth != null＝warn", [titles(rt('{"rules":{"msgs":{".read":"auth != null"}}}'), "danger").length, titles(rt('{"rules":{"msgs":{".read":"auth != null"}}}'), "warn")], [0, ["ログインしている人なら誰でも読める場所があります（Realtime Database・database.rules.json）"]]);
t("B5：既存の true の判定は変わらない", titles(rt('{"rules":{".read":true,".write":false}}'), "danger"), ["Realtime Database 全体を、誰でも読める状態です（database.rules.json）"]);
t("B5：文字列の中の // は落とさない", JSON.parse(looseJson('{"a":"http://x.test/*y*/","b":1,}')), { a: "http://x.test/*y*/", b: 1 });
// N4：コメント入りでも壊れた JSON でも、無言にしない
t("N4：コメント入りの database.rules.json で無言にならない", titles(rt(COMMENTED), "warn").length + titles(rt(COMMENTED), "danger").length > 0, true);
t("N4：壊れた JSON＝warn「読めませんでした」", titles(rt('{"rules": {".read": '), "warn"), ["database.rules.json を読めませんでした"]);
t("N4：JSON でない中身も warn", titles(rt("not json"), "warn"), ["database.rules.json を読めませんでした"]);
t("B5：ルールが無い {}（rules が空）は何も出さない", ["danger", "warn"].map((k) => titles(rt('{"rules":{}}'), k).length), [0, 0]);
// 変えない物：正しい持ち主ルール・一部の read: true は今までどおり
t("不変：持ち主のルールだけ＝何も出ない", ["danger", "warn", "info"].map((k) => titles(run({ "firestore.rules": "service cloud.firestore {\n  match /databases/{database}/documents {\n    match /users/{userId} {\n      allow read, write: if request.auth != null && request.auth.uid == userId;\n    }\n  }\n}\n" }), k).length), [0, 0, 0]);
// ---- レビュー r1（BLOCK）の指摘
t("r1-1：if true && true は danger（読めない行にしない）", [titles(run({ "firestore.rules": FS("allow read, write: if true && true;") }), "danger"), unresolvedOf("allow read, write: if true && true;").length], [["誰でも読み書きできる状態です（firestore.rules）"], 0]);
t("r1-1：if isSignedIn() && customCheck() は読めない行", unresolvedOf("allow read: if isSignedIn() && customCheck();").length, 1);
t("r1-1：request.auth != null && customCheck() も読めない行", unresolvedOf("allow read: if request.auth != null && customCheck();").length, 1);
t("r1-1：true && 関数 は読めない行", unresolvedOf("allow read: if true && isOk();").length, 1);
t("r1-1：auth && データの検査 は今までどおり無言", unresolvedOf("allow create: if request.auth != null && request.resource.data.name is string;").length, 0);
t("r1-1：持ち主の照合＋データの検査 は無言", unresolvedOf("allow write: if request.auth.uid == userId && request.resource.data.size() < 10;").length, 0);
const G2 = (files) => geminiTitles(run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', ...files }));
const FBCFG = `const firebaseConfig = {\n  apiKey: "${AK}",\n  authDomain: "d.firebaseapp.com",\n};\n`;
t("r1-2：firebaseConfig の直後の new GoogleGenAI({ apiKey: AIza }) を見逃さない", G2({ "src/a.ts": FBCFG + `const ai = new GoogleGenAI({ apiKey: "${AK}2" });\n` }), ["Gemini のキーがブラウザ側に出ています"]);
t("r1-2：同じ行（配布物）の firebaseConfig と Gemini でも Gemini 側だけを danger にし（info は同じ行なので出さない＝安全側）", (() => { const F = run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "dist/a.js": `var c={apiKey:"${AK}",authDomain:"d"},g=new GoogleGenAI({apiKey:"${AK}2"});\n` }); return [F.danger.filter((f) => f.title.startsWith("Gemini")).map((f) => f.evidence.length), F.info.length]; })(), [[1], 0]);
t("r1-2：Gemini の鍵の行を Firebase の apiKey は正常と言わない", run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "src/a.ts": `new GoogleGenAI({ apiKey: "${AK}" });\n` }).info.length, 0);
t("r1-3：閉じていない /* は parse 失敗（warn）", [titles(rt('{"rules":{}}/*'), "warn"), titles(rt('{"rules":{}}\n/* 閉じない'), "warn")], [["database.rules.json を読めませんでした"], ["database.rules.json を読めませんでした"]]);
t("r1-3：looseJson は閉じていない /* で例外", (() => { try { looseJson('{"a":1}/*'); return "no throw"; } catch (e) { return "throw"; } })(), "throw");
console.log(fail ? `\n${fail} FAILED` : "\nALL PASS"); process.exit(fail ? 1 : 0);
