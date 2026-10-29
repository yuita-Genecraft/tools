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
  ["#03 || true", "allow read, write: if request.auth != null || true;", 5], ["#06 括弧", "allow read, write: if (request.auth != null);", 5],
  ["#15 関数", "allow read, write: if isSignedIn();", 5],
]) {
  const u = unresolvedOf(body);
  t(`B2/N2：${name}＝無言にしない（行の実物つき）`, [u.length, u[0] && u[0].evidence[0].loc, u[0] && u[0].evidence[0].code.startsWith("allow")], [1, `firestore.rules:${lineNo}`, true]);
}
t("B2：件数が見出しに出る", unresolvedOf("allow read: if f(1);\n      allow write: if g(2);")[0].title, "判定できなかった allow の行があります（2 行・firestore.rules）");
t("B2：持ち主の照合（&&・uid ==）・false は無言（言い過ぎを増やさない）", ["allow read: if request.auth.uid == userId;", "allow write: if false;", "allow read: if resource.data.owner == request.auth.uid;"].map((b) => unresolvedOf(b).length), [0, 0, 0]);
t("B2：&& でつないだ条件は、読める項だけでも判定できなかった行（全体が1つの形に一致した時だけ読む）", unresolvedOf("allow read, write: if request.auth != null && request.auth.uid == userId;").length, 1);
// 条件や ops が次の行に続く文は、; か } までつないで読む（次の行は allow を持たないので、つながないと見えない）
t("B2：条件が次の行（auth・true）・ops が複数行は、つないで読んで判定する（無言にも読めない行にもしない）", [["allow read, write: if\n        request.auth != null;", "danger", "ログインすれば、すべての文書を読み書きできます（firestore.rules）"], ["allow read, write: if\n        true;", "danger", "誰でも読み書きできる状態です（firestore.rules）"], ["allow read,\n        write: if true;", "danger", "誰でも読み書きできる状態です（firestore.rules）"]].map(([b, k, ti]) => [titles(run({ "firestore.rules": FS(b) }), k), unresolvedOf(b).length]), [[["ログインすれば、すべての文書を読み書きできます（firestore.rules）"], 0], [["誰でも読み書きできる状態です（firestore.rules）"], 0], [["誰でも読み書きできる状態です（firestore.rules）"], 0]]);
t("B2：コメントの中の「allow」という語では出さない", unresolvedOf("/* allow only the owner */\n      // allow nothing here\n      allow write: if false;").length, 0);
// B3：request.auth.uid != null
t("B3：request.auth.uid != null が全体＝danger（ログインすれば…）", titles(run({ "firestore.rules": FS("allow read, write: if request.auth.uid != null;") }), "danger"), ["ログインすれば、すべての文書を読み書きできます（firestore.rules）"]);
// B4：Gemini のキー（P1-1）
const AK = ["AIza", "SyFAKEFAKEFAKEFAKEFAKE_12345-abc"].join("");
const geminiTitles = (F) => F.danger.filter((f) => f.title.startsWith("Gemini のキー")).map((f) => f.title);
t("B4：@google/genai ＋ ソースに AIza＝danger", geminiTitles(run({ "src/ai.ts": `import { GoogleGenAI } from "@google/genai";\nconst ai = new GoogleGenAI({ apiKey: "${AK}" });\n` })), ["Gemini のキーがブラウザ側に出ています"]);
t("B4：VITE_GEMINI_API_KEY=AIza…（.env）が素通りしない", geminiTitles(run({ "package.json": '{"dependencies":{"@google/generative-ai":"^0.21.0"}}', ".env": `VITE_GEMINI_API_KEY=${AK}\n` }, { envStatus: new Map([[".env", "untracked_ignored"]]) })), ["Gemini のキーがブラウザ側に出ています"]);
t("B4：配布物（dist）のオブジェクトのプロパティの AIza を拾う（danger）", geminiTitles(run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "dist/assets/a.js": `var c="generativelanguage.googleapis.com";var g=new GoogleGenAI({apiKey:"${AK}"});\n` })), ["Gemini のキーがブラウザ側に出ています"]);
t("B4：配布物の、プロパティの値と読めない AIza（var k=\"…\"）は言い切らず warn（迷ったら warn）", (() => { const F = run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "dist/assets/a.js": `var c="generativelanguage.googleapis.com";var k="${AK}";\n` }); return [geminiTitles(F), F.warn.map((f) => f.title)]; })(), [[], ["Firebase の設定か Gemini のキーか判定できなかった AIza… があります"]]);
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
t("不変：持ち主のルールだけ＝何も出ない", ["danger", "warn", "info"].map((k) => titles(run({ "firestore.rules": "service cloud.firestore {\n  match /databases/{database}/documents {\n    match /users/{userId} {\n      allow read, write: if request.auth.uid == userId;\n    }\n  }\n}\n" }), k).length), [0, 0, 0]);
// ---- レビュー r1（BLOCK）の指摘
t("r1-1：if true && true は判定できなかった行（全体がちょうど true の時だけ true）", [titles(run({ "firestore.rules": FS("allow read, write: if true && true;") }), "danger"), unresolvedOf("allow read, write: if true && true;").length], [[], 1]);
t("r1-1：if isSignedIn() && customCheck() は読めない行", unresolvedOf("allow read: if isSignedIn() && customCheck();").length, 1);
t("r1-1：request.auth != null && customCheck() も読めない行", unresolvedOf("allow read: if request.auth != null && customCheck();").length, 1);
t("r1-1：true && 関数 は読めない行", unresolvedOf("allow read: if true && isOk();").length, 1);
t("r1-1：auth && データの検査 は判定できなかった行", unresolvedOf("allow create: if request.auth != null && request.resource.data.name is string;").length, 1);
t("r1-1：持ち主の照合＋読める比較も、&& を含むので判定できなかった行", unresolvedOf("allow write: if request.auth.uid == userId && request.resource.data.n < 10;").length, 1);
const G2 = (files) => geminiTitles(run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', ...files }));
const FBCFG = `const firebaseConfig = {\n  apiKey: "${AK}",\n  authDomain: "d.firebaseapp.com",\n};\n`;
t("r1-2：firebaseConfig の直後の new GoogleGenAI({ apiKey: AIza }) を見逃さない", G2({ "src/a.ts": FBCFG + `const ai = new GoogleGenAI({ apiKey: "${AK}2" });\n` }), ["Gemini のキーがブラウザ側に出ています"]);
t("r1-2：同じ行（配布物）の firebaseConfig と Gemini でも Gemini 側だけを danger にし（info は同じ行なので出さない＝安全側）", (() => { const F = run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "dist/a.js": `var c={apiKey:"${AK}",authDomain:"d"},g=new GoogleGenAI({apiKey:"${AK}2"});\n` }); return [F.danger.filter((f) => f.title.startsWith("Gemini")).map((f) => f.evidence.length), F.info.length]; })(), [[1], 0]);
t("r1-2：Gemini の鍵の行を Firebase の apiKey は正常と言わない", run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "src/a.ts": `new GoogleGenAI({ apiKey: "${AK}" });\n` }).info.length, 0);
t("r1-3：閉じていない /* は parse 失敗（warn）", [titles(rt('{"rules":{}}/*'), "warn"), titles(rt('{"rules":{}}\n/* 閉じない'), "warn")], [["database.rules.json を読めませんでした"], ["database.rules.json を読めませんでした"]]);
t("r1-3：looseJson は閉じていない /* で例外", (() => { try { looseJson('{"a":1}/*'); return "no throw"; } catch (e) { return "throw"; } })(), "throw");
// ---- レビュー r2（BLOCK・P1×3）の指摘（例はレビューのまま）
t("r2-1：true && request.auth != null も、&& を含むので判定できなかった行（danger にも無言にもしない）", [unresolvedOf("allow read, write: if true && request.auth != null;").length, titles(run({ "firestore.rules": FS("allow read, write: if true && request.auth != null;") }), "danger")], [1, []]);
t("r2-1：&& を含む条件は、読める項だけでも全部 判定できなかった行", ["true && request.resource.data.n is int", "true && request.auth.uid == id", "request.auth != null && request.resource.data.n is int", "request.auth != null && request.auth.uid == id"].map((c) => unresolvedOf(`allow write: if ${c};`).length), [1, 1, 1, 1]);
const NL = "\n" + " ".repeat(80);
t("r2-2：apiKey: の後に改行と長い空白があっても、同じ { } に authDomain があれば Firebase の鍵（Gemini の danger にしない）", G2({ "src/fb.ts": `const firebaseConfig = {\n  apiKey:${NL}"${AK}",\n  authDomain: "d.firebaseapp.com",\n};\n` }), []);
t("r2-2：キーを JSON 形式（引用符つき）で書いた firebaseConfig も Firebase の鍵", G2({ "src/fb.ts": `const c = { "apiKey": "${AK}", "authDomain": "d", "projectId": "p" };\n` }), []);
t("r2-3：値の文字列に authDomain があるだけの Gemini の設定は Gemini の danger（レビューの例そのまま）", G2({ "src/ai.ts": `new GoogleGenAI({ apiKey: "${AK}", note: "authDomain" });\n` }), ["Gemini のキーがブラウザ側に出ています"]);
t("r2-3：その行を「Firebase の apiKey は正常」と言わない", run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "src/ai.ts": `new GoogleGenAI({ apiKey: "${AK}", note: "authDomain" });\n` }).info.length, 0);
t("r2-3：コメントの中の authDomain・別の { } にある authDomain では除外しない", G2({ "src/ai.ts": `const a = { authDomain: "x" };\nnew GoogleGenAI({ apiKey: "${AK}" /* authDomain */ });\n` }), ["Gemini のキーがブラウザ側に出ています"]);
const UNSURE = "Firebase の設定か Gemini のキーか判定できなかった AIza… があります";
const unsureOf = (files) => run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', ...files });
t("r2-3：{ } が読み切れない（閉じない括弧）時は danger にも「正常」にもせず warn", (() => { const F = unsureOf({ "src/fb.ts": `const firebaseConfig = {\n  apiKey: "${AK}",\n  authDomain: "d",\n` }); return [geminiTitles(F), titles(F, "warn"), F.info.length]; })(), [[], [UNSURE], 0]);
t("r2-3：{ } の外の apiKey（const apiKey = …）はプロパティの値と読めない＝danger にせず warn", [G2({ "src/ai.ts": `const apiKey = "${AK}";\nconst firebaseConfig = { authDomain: "d" };\n` }), run({ "package.json": '{"dependencies":{"@google/genai":"^1"}}', "src/ai.ts": `const apiKey = "${AK}";\n` }).warn.length], [[], 1]);
// ---- レビュー r3（BLOCK）：読み切れない時は warn（迷ったら warn）。danger は「Firebase の設定の中ではない」と読めた時だけ
t("r3-1：名前と : の間のコメント（apiKey /* c */ : \"AIza…\"）を飛ばして Firebase の鍵と読む（danger にしない）", (() => { const F = unsureOf({ "src/fb.ts": `const c = { apiKey /* comment */ : "${AK}", authDomain: "d" };\n` }); return [geminiTitles(F), titles(F, "warn"), F.info.length]; })(), [[], [], 0]);
t("r3-1：// コメントをはさんでも同じ", geminiTitles(unsureOf({ "src/fb.ts": `const c = {\n  apiKey // c\n  : "${AK}",\n  authDomain: "d",\n};\n` })), []);
t("r3-2：正規表現リテラルの } で範囲が崩れたら、danger にせず warn（レビューの例そのまま）", (() => { const F = unsureOf({ "src/fb.ts": `const re = /}/; const c = { apiKey: "${AK}", authDomain: "d" };\n` }); return [geminiTitles(F), titles(F, "warn"), F.info.length]; })(), [[], [UNSURE], 0]);
t("r3-2：正規表現リテラルの { で崩れても warn", titles(unsureOf({ "src/fb.ts": `const re = /{/; const c = { apiKey: "${AK}", authDomain: "d" };\n` }), "warn"), [UNSURE]);
t("r3-2：warn には行の実物がつく", unsureOf({ "src/fb.ts": `const re = /}/;\nconst c = { apiKey: "${AK}", authDomain: "d" };\n` }).warn[0].evidence.map((e) => e.loc), ["src/fb.ts:2"]);
t("r3：鍵のプロパティ名が取れない（[k]: \"AIza…\"）時は warn", (() => { const F = unsureOf({ "src/a.ts": `const o = { [k]: "${AK}" };\n` }); return [geminiTitles(F), titles(F, "warn")]; })(), [[], [UNSURE]]);
t("r3：danger は、プロパティの値と読めて Firebase の設定ではないと読めた時だけ（new GoogleGenAI({ apiKey: \"AIza…\" })）", geminiTitles(unsureOf({ "src/a.ts": `new GoogleGenAI({ apiKey: "${AK}" });\n` })), ["Gemini のキーがブラウザ側に出ています"]);
t("r5：Gemini の SDK の生成の第1引数に引用符の文字列で AIza… が直接入る形は danger（new GoogleGenerativeAI(\"AIza…\")・new GoogleGenAI(\"AIza…\")・第2引数が付いても）", ['new GoogleGenerativeAI("AIK")', "new GoogleGenAI('AIK')", 'new GoogleGenAI( "AIK" , opts)', 'const ai = new GoogleGenerativeAI("AIK");'].map((c) => geminiTitles(unsureOf({ "src/a.ts": c.replace("AIK", AK) + "\n" })).length), [1, 1, 1, 1]);
t("r5：第1引数が識別子（new GoogleGenAI(key)）は danger にならない（鍵の文字が無いので何も出ない）", (() => { const F = unsureOf({ "src/a.ts": "const key = process.env.K;\nnew GoogleGenAI(key);\n" }); return [geminiTitles(F), F.warn.length]; })(), [[], 0]);
t("r5：読めない形は warn のまま（連結・テンプレート・var 単独・別の呼び出し f(\"AIza…\")・生成の呼び出しでない第2引数）", ['new GoogleGenAI("AIK" + x)', "new GoogleGenAI(`AIK`)", 'var k = "AIK";', 'f("AIK")', 'new GoogleGenAI(opts, "AIK")', 'new Other("AIK")'].map((c) => { const F = unsureOf({ "src/a.ts": c.replace("AIK", AK) + "\n" }); return [geminiTitles(F).length, titles(F, "warn").length]; }), [[0, 1], [0, 1], [0, 1], [0, 1], [0, 1], [0, 1]]);
t("r3：Gemini の痕跡が無ければ読み切れなくても何も言わない（N3）", run({ "src/fb.ts": `const re = /}/; const c = { apiKey: "${AK}", authDomain: "d" };\n` }).warn.length, 0);
// ---- レビュー r4（BLOCK）：danger は肯定の条件が揃った時だけ。読み取れなかった値は全部 warn（既定は unknown）
const cfgWith = (v) => `const c = { apiKey: ${v}, authDomain: "d" };\n`;
for (const [name, v] of [["括弧（レビューの例そのまま）", `("${AK}")`], ["テンプレート文字列", `\`${AK}\``], ["連結", `"${AK}" + suffix`], ["三項演算子", `x ? "${AK}" : "y"`], ["関数呼び出しの引数", `f("${AK}")`]]) {
  const F = unsureOf({ "src/fb.ts": cfgWith(v) });
  t(`r4：apiKey の値が ${name}＝読めた Firebase の設定でも danger にせず、正常とも言わず warn`, [geminiTitles(F), titles(F, "warn"), F.info.length], [[], [UNSURE], 0]);
}
t("r4：スプレッド（{ ...base, apiKey: \"AIza…\" }）は直下のプロパティ名を取り切れない＝warn", (() => { const F = unsureOf({ "src/fb.ts": `const c = { ...base, apiKey: "${AK}" };\n` }); return [geminiTitles(F), titles(F, "warn")]; })(), [[], [UNSURE]]);
t("r4：計算されたキー（{ [k]: 1, apiKey: \"AIza…\" }）も warn", (() => { const F = unsureOf({ "src/fb.ts": `const c = { [k]: 1, apiKey: "${AK}" };\n` }); return [geminiTitles(F), titles(F, "warn")]; })(), [[], [UNSURE]]);
t("r4：Firebase の設定のキーが並ぶ { } で apiKey 以外のプロパティに AIza…＝言い切らず warn", (() => { const F = unsureOf({ "src/fb.ts": `const c = { key: "${AK}", authDomain: "d" };\n` }); return [geminiTitles(F), titles(F, "warn")]; })(), [[], [UNSURE]]);
t("r4：読めた Firebase の設定は今までどおり無言（Gemini の痕跡があっても）", (() => { const F = unsureOf({ "src/fb.ts": cfgWith(`"${AK}"`) }); return [geminiTitles(F), F.warn.length, F.info.length]; })(), [[], 0, 1]);
// ---- レビュー r5（BLOCK）：文字列の終端のエスケープ・別名の呼び出し
t("r5-1：SDK の引数の文字列の \\\" は終端ではない（連結の直書き扱いにしない・レビューの例そのまま）", (() => { const F = unsureOf({ "src/a.ts": `new GoogleGenAI("${AK}\\",)" + suffix);\n` }); return [geminiTitles(F), titles(F, "warn")]; })(), [[], [UNSURE]]);
t("r5-1：エスケープされた \\ で終わる文字列（\"AIza…\\\\\"）は本当の終端として danger", geminiTitles(unsureOf({ "src/a.ts": `new GoogleGenAI("${AK}\\\\");\n` })).length, 1);
t("r5-1：閉じない文字列は読み切れない＝warn", (() => { const F = unsureOf({ "src/a.ts": `new GoogleGenAI("${AK}\n` }); return [geminiTitles(F), titles(F, "warn")]; })(), [[], [UNSURE]]);
t("r5-2：$GoogleGenAI(\"AIza…\") は別の名前＝danger にしない（レビューの例そのまま）", (() => { const F = unsureOf({ "src/a.ts": `$GoogleGenAI("${AK}");\n` }); return [geminiTitles(F), titles(F, "warn")]; })(), [[], [UNSURE]]);
t("r5-2：_GoogleGenAI(・xGoogleGenAI( も別の名前", ["_GoogleGenAI", "xGoogleGenAI", "MyGoogleGenerativeAI"].map((n) => geminiTitles(unsureOf({ "src/a.ts": `${n}("${AK}");\n` })).length), [0, 0, 0]);
t("r5-2：名前空間つき（genai.GoogleGenAI(\"AIza…\")）は SDK の呼び出しとして danger（今の扱いのまま）", geminiTitles(unsureOf({ "src/a.ts": `new genai.GoogleGenAI("${AK}");\n` })).length, 1);
// ---- 判定の抜け（fbcheck repo 審査 BLOCK）：条件の項は完全一致の文法で読む。READMEの限界の3つ（関数・括弧・||）は、全部「判定できなかった行」に入る
const UR = (c) => unresolvedOf(`allow read: if ${c};`);
t("g-1：レビューの例（resource.data.x == someFunction()）は判定できなかった行", UR("resource.data.x == someFunction()").length, 1);
t("g-1：関数・メソッドの呼び出し（右辺・左辺・メソッド）はどれも判定できなかった行", ["request.auth.uid == getOwner(x)", "getOwner(x) == request.auth.uid", "request.resource.data.size() < 10", "resource.data.keys().hasAll([\"a\"])", "request.time < timestamp.date(2099, 1, 1) && request.auth != null", "request.auth.uid == userId && resource.data.x == f()", "isSignedIn() && request.auth != null"].map((c) => UR(c).length), [1, 1, 1, 1, 1, 1, 1]);
t("g-2：括弧は判定できなかった行（比較の中・全体・片側）", ["(request.auth != null)", "request.auth.uid == (userId)", "request.auth != null && (resource.data.x == 1)", "(true)"].map((c) => UR(c).length), [1, 1, 1, 1]);
t("g-3：|| は判定できなかった行", ["request.auth != null || true", "resource.data.public == true || request.auth.uid == userId", "request.auth.uid == userId || isAdmin()"].map((c) => UR(c).length), [1, 1, 1]);
t("g-4：混在（&& の片方だけ読めない）は判定できなかった行・danger にも auth にもしない", [UR("true && isOk()").length, titles(run({ "firestore.rules": FS("allow read, write: if true && isOk();") }), "danger").length, titles(run({ "firestore.rules": FS("allow read, write: if request.auth != null && isOk();") }), "danger").length], [1, 0, 0]);
t("g-5：1つの比較・型の検査・false は無言", ["request.auth.uid == userId", "resource.data.owner == request.auth.uid", "request.auth.token.admin == true", "request.auth.uid == \"alice\"", "request.resource.data.name is string", "resource.data.public == true", "false"].map((c) => UR(c).length), [0, 0, 0, 0, 0, 0, 0]);
t("g-6：true を含む &&・|| は true として扱わない（全体がちょうど true の時だけ danger）", [UR("true && request.auth.uid == \"alice\"").length, UR("true || someFunction()").length, UR("true && request.auth.uid == null").length, titles(run({ "firestore.rules": FS("allow read, write: if true && request.auth.uid == \"alice\";") }), "danger"), titles(run({ "firestore.rules": FS("allow read, write: if true || someFunction();") }), "danger")], [1, 1, 1, [], []]);
t("g-7：danger の判定（全体がちょうど true・条件なし・auth 全体・期限）は変わらない", [FS("allow read, write: if true;"), FS("allow read, write;"), FS("allow read, write: if request.auth != null;"), FS("allow read, write: if request.time < timestamp.date(2099, 1, 1);")].map((b) => run({ "firestore.rules": b }).danger.length), [1, 1, 1, 1]);
t("g-8：FBCHECK_VERSION は 0.3.1", /const FBCHECK_VERSION = "0\.3\.1";/.test(src), true);
// ---- 表から機械的に作る試験（レビュー r1 の指摘：手で思いついた例だけにしない）。項 × つなぎ × 改行の位置 の全組み合わせ
{
  const READ = ["request.auth.uid == userId", "resource.data.owner == request.auth.uid", "request.resource.data.name is string", "request.auth.uid == \"alice\"", "false"];
  const ODD = ["someFunction()", "resource.data.x == someFunction()", "(request.auth != null)", "request.resource.data.size() < 10", "isOk()"];
  const ANY = ["true", "request.auth != null"];
  const TERMS = [...READ, ...ODD, ...ANY];
  const JOIN = [" && ", " || "];
  // 改行の入れ方：なし／if の直後／つなぎの前／つなぎの後／; の前／ops の途中
  const layout = (ops, cond, k, join) => {
    const parts = join ? cond.split(join) : [cond];
    const c = k === 2 && join ? parts.join("\n  " + join.trim() + " ") : k === 3 && join ? parts.join(" " + join.trim() + "\n  ") : cond;
    return (k === 5 ? `allow ${ops[0]},\n  ${ops[1]}` : `allow ${ops.join(", ")}`) + (k === 1 ? ": if\n  " : ": if ") + c + (k === 4 ? "\n;" : ";");
  };
  const bad = [];
  let n = 0;
  const check = (label, body, wantUnres, wantDanger) => {
    n++;
    const u = unresolvedOf(body).length, d = run({ "firestore.rules": FS(body) }).danger.length;
    if (u !== wantUnres || d !== wantDanger) bad.push(`${label} [${body.replace(/\n/g, "\\n")}] unres=${u}/${wantUnres} danger=${d}/${wantDanger}`);
  };
  for (let k = 0; k <= 5; k++) {
    for (const ops of [["read", "write"], ["get", "list"]]) {
      // 1つの項：読める形は無言（改行の位置によらない）・読めない形は判定できなかった行
      for (const t1 of READ) check(`単独読める k${k}`, layout(ops, t1, k), 0, 0);
      for (const t1 of ODD) check(`単独読めない k${k}`, layout(ops, t1, k), 1, 0);
      check(`単独 true k${k}`, layout(ops, "true", k), 0, 1);
      check(`単独 auth k${k}`, layout(ops, "request.auth != null", k), 0, 1);
      // 2項・3項：&& か || を含む条件は、項がすべて読めても、true／auth を含んでも、判定できなかった行 1 件・danger 0 件
      for (const j of JOIN) for (const a of TERMS) for (const b of TERMS) {
        check(`2項 k${k}`, layout(ops, a + j + b, k, j), 1, 0);
        for (const c3 of ["true", "someFunction()", "request.auth.uid == userId"]) check(`3項 k${k}`, layout(ops, a + j + b + j + c3, k, j), 1, 0);
      }
    }
  }
  t(`表から作った試験 ${n} 件：&& か || を含む条件は、読める項だけでも true を含んでも 判定できなかった行（danger にしない）／単独の項は読める形だけ無言`, bad.slice(0, 5), []);
  // 指摘の3例（レビューのまま）
  t("r1 の例1：true || someFunction() は判定できなかった行", [UR("true || someFunction()").length, run({ "firestore.rules": FS("allow read: if true || someFunction();") }).danger.length], [1, 0]);
  t("r1 の例2：次の行に && someFunction() が続く条件は判定できなかった行", [unresolvedOf("allow read: if request.auth.uid == userId\n        && someFunction();").length, unresolvedOf("allow read: if request.auth.uid == userId\n        && someFunction();")[0].evidence[0].code], [1, "allow read: if request.auth.uid == userId && someFunction();"]);
  t("r1 の例3：true && request.auth.uid == \"alice\" は danger にならず判定できなかった行", [run({ "firestore.rules": FS("allow write: if true && request.auth.uid == \"alice\";") }).danger.length, UR("true && request.auth.uid == \"alice\"").length], [0, 1]);
}
// ---- レビュー r2（BLOCK・P1×2）：つなぐ処理の打ち切り。終わり（; か }）に届かない文は読めない行・次の allow／match をまたがない
{
  const raw = (body) => run({ "firestore.rules": body }), RAW = (inner) => `service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n${inner}`;
  const gap = (n) => "\n".repeat(n);
  const rows = [0, 1, 5, 19, 20, 21, 25, 40].map((n) => { const F = raw(RAW(`      allow write: if true${gap(n)}        && someFunction();\n    }\n  }\n}\n`)); return [n, F.danger.length, F.warn.filter(UNRES).length]; });
  t("r2-a：空行が何行あっても、次に && someFunction(); が続く true は danger にしない（0〜19 行は つないで unresolved、20 行以上は終わりに届かず unresolved）", rows.map(([n, d, u]) => [d, u]), rows.map(() => [0, 1]));
  t("r2-a：ファイルの終わりが allow write: if true（; も } も無い）は danger にせず unresolved", (() => { const F = raw(RAW("      allow write: if true")); return [F.danger.length, F.warn.filter(UNRES).length]; })(), [0, 1]);
  t("r2-a：終わりに届いた普通の形（空行をはさんだ true;）は今までどおり danger", raw(RAW(`      allow write: if${gap(3)}        true;\n    }\n  }\n}\n`)).danger.length, 1);
  const B = (second) => raw(`service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      allow read: if false\n    ${second}\n  }\n}\n`);
  const FB = B("} match /posts/{id} { allow read: if true; }");
  t("r2-b：allow read: if false の次行が「} match /posts/{id} { allow read: if true; }」でも、posts の read: true を全体スコープの danger にしない（posts だけの warn＋; の無い allow read: if false は判定できなかった行）", [FB.danger.length, FB.warn.map((f) => f.title)], [0, ["誰でも読める場所があります（firestore.rules）", "判定できなかった allow の行があります（1 行・firestore.rules）"]]);
  // r3：同じ行に完結した allow と未完の allow が並ぶ形（完結が先・未完が後・次行に別の allow）。完結した方の danger は出し、未完の方だけ unresolved
  const MIX = raw(`service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      allow write: if true; allow read: if false\n      allow get: if false;\n    }\n  }\n}\n`);
  t("r3：同じ行の「allow write: if true; allow read: if false」＋次行に別の allow でも、完結した write: true の danger は出し、未完の allow read は unresolved", [MIX.danger.map((f) => f.title), MIX.warn.filter(UNRES).length], [["誰でも書き込める状態です（firestore.rules）"], 1]);
  const MIX2 = raw(RAW("      allow read; allow write: if false\n      match /x/{y} { allow get: if true; }\n    }\n  }\n}\n"));
  t("r3：完結した条件なしの allow read; も、同じ行の未完の allow の前なら拾う（danger）・未完は unresolved", [MIX2.danger.length, MIX2.warn.filter(UNRES).length], [1, 1]);
  t("r2-b：終わりの無い allow の次の行に別の allow・match があれば、そこで打ち切って unresolved（次の行の allow は次の行として読む）", (() => { const F = B("allow write: if true;"); return [F.danger.length, F.warn.filter(UNRES).length]; })(), [1, 1]);
}
// ---- レビュー r3（BLOCK）：同じ行に完結した allow と未完の allow が並ぶ形。文の切り出しは一度だけ頭から読む読み手（readAllows）。
// 完結した文 × 別の文 × 区切り（空白・改行・コメント）× 並び順 を機械的に作る。完結した無認証の書き込みは必ず danger に出て、別の文は自分の分だけ unresolved になる
{
  const raw = (body) => run({ "firestore.rules": body }), RAW = (inner) => `service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n${inner}`;
  const A = ["allow write: if true;", "allow write:\n   if\n   true\n   ;", "allow write: if true /* ; } { */;", "allow write: if /* x */ true;", "allow write : if  true ;"];
  const Bs = [["allow read: if false", 1], ["allow get: if f();", 1], ["allow list: if true && g();", 1], ["allow create: if resource.data.x == \";\";", 0], ["allow update: if resource.data.x == '{;}';", 0], ["allow read: if false /* ; } */", 1]];
  const SEP = [" ", "\n", "\n\n   // ; { }\n   ", " /* } ; */ ", "\n   /* allow read: if true; */\n   "];
  const bad = []; let n = 0;
  for (const a of A) for (const [b, nu] of Bs) for (const sep of SEP) for (const order of ["AB", "BA", "ABA"]) {
    const body = (order === "AB" ? [a, b] : order === "BA" ? [b, a] : [a, b, a]).join(sep);
    const F = raw(`service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      ${body}\n    }\n  }\n}\n`);
    const u = F.warn.filter(UNRES).length, d = F.danger.map((f) => f.title);
    n++;
    if (u !== nu || d.length !== 1 || !d[0].startsWith("誰でも書き込める")) bad.push(`${order} [${body.replace(/\n/g, "\\n")}] unres=${u}/${nu} danger=${JSON.stringify(d)}`);
  }
  t(`r3：完結した allow write: if true; は、未完・読めない・読める別の文と並んでも（区切り・並び順 ${n} 通り）danger に出て、別の文は自分の分だけ unresolved`, bad.slice(0, 4), []);
  const F2 = raw(`service cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      allow write: if true; allow read: if false\n      allow get: if false;\n    }\n  }\n}\n`);
  t("r3 の例：allow write: if true; allow read: if false の次行が allow get: if false;", [F2.danger.map((f) => f.title), F2.warn.filter(UNRES).length], [["誰でも書き込める状態です（firestore.rules）"], 1]);
  // r4：括弧が閉じていない文（allow read: if f( ）の次行に完結した allow がある形。後続の allow で打ち切り、後続の danger を落とさない
  for (const [name, head] of [["括弧が閉じていない", "allow read: if f("], ["[ が閉じていない", "allow read: if x in ["], ["括弧の中に文字列", "allow read: if f(\"a;b\""], ["括弧が深い", "allow read: if f(g("]]) for (const sep of ["\n      ", " ", "\n\n      // ; )\n      "]) {
    const F = raw(RAW(`      ${head}${sep}allow write: if true;\n    }\n  }\n}\n`));
    t(`r4：${name}文の次に完結した allow write: if true; が続いても、その danger は出し、括弧の文だけ unresolved [${sep.replace(/\n/g, "\\n")}]`, [F.danger.length, F.warn.filter(UNRES).length], [1, 1]);
  }
  const F4 = raw(RAW("      allow read: if f(\n      match /x/{y} { allow get: if true; }\n    }\n  }\n}\n"));
  t("r4：括弧が閉じていない文の次が match でも、そこで打ち切る（x の get: true は全体の danger にしない）", [F4.danger.length, F4.warn.filter(UNRES).length], [0, 1]);
  // 閉じていない ( [ { と、その後に来る allow・match・}・ファイルの終わり の組み合わせ（機械的に）。完結した後続の allow write: if true; は必ず danger に出て、閉じていない文だけが unresolved
  {
    const OPEN = ["allow read: if f(", "allow read: if f(g(", "allow read: if x in [", "allow read: if f([", "allow read: if f(\"a;)\"", "allow read: if x == {", "allow read: if f({"];
    const NEXT = [["allow write: if true;", 1], ["match /x/{y} { allow write: if true; }", 1], ["}", 0], ["", 0]];
    const SEP4 = ["\n      ", " ", "\n      // ( [ {\n      ", " /* ) ] } */ "];
    const bad4 = []; let n4 = 0;
    for (const o of OPEN) for (const [nx, dng] of NEXT) for (const sp of SEP4) {
      const F = raw(RAW(`      ${o}${sp}${nx}\n    }\n  }\n}\n`));
      const u = F.warn.filter(UNRES).length, d = F.danger.length;
      n4++;
      if (u !== 1 || d !== dng) bad4.push(`[${o}${sp.replace(/\n/g, "\\n")}${nx}] unres=${u}/1 danger=${d}/${dng}`);
    }
    t(`r4：閉じていない ( [ { の文は、後に allow・match・}・終わりが来ても ${n4} 通り、その文だけ unresolved（後続の完結した allow・match の中の allow の danger は落とさない）`, bad4.slice(0, 4), []);
  }
  t("コメント・文字列の中の ; { } は文の区切りにしない", (() => { const F = raw(RAW("      // allow write: if true;\n      /* allow read: if true; */\n      allow read: if resource.data.s == \"; } {\";\n    }\n  }\n}\n")); return [F.danger.length, F.warn.length]; })(), [0, 0]);
}
console.log(fail ? `\n${fail} FAILED` : "\nALL PASS"); process.exit(fail ? 1 : 0);
