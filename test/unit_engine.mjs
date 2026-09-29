// engine.js の部品を直接たたく（.gitignore の読み・ルールの読み）
import fs from "node:fs"; import vm from "node:vm";
const src = fs.readFileSync(new URL("../fbcheck-web/engine.js", import.meta.url), "utf8");
const ctx = {}; vm.createContext(ctx); vm.runInContext(src + "\n;globalThis.E={gitignoreCovers, matchChains, allowsIn, isWholeScope, globToRegex, runChecks};", ctx);
const { gitignoreCovers, matchChains, allowsIn, isWholeScope, runChecks } = ctx.E;
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
console.log(fail ? `\n${fail} FAILED` : "\nALL PASS"); process.exit(fail ? 1 : 0);
