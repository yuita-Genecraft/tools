// 判定本体（engine.js）を 24 件の入力で直接たたき、出た物を並べる（修正の前後の差を見る用）
// 使い方: node test/probe24.mjs [engine.js のパス] [番号2桁]   既定は fbcheck-web/engine.js・全件
import fs from "node:fs"; import vm from "node:vm";
const J = (...a) => a.join("");
const args = process.argv.slice(2);
const only = args.find((a) => /^\d\d$/.test(a));
const enginePath = args.find((a) => !/^\d\d$/.test(a)) || new URL("../fbcheck-web/engine.js", import.meta.url).pathname;
const ctx = {}; vm.createContext(ctx); vm.runInContext(fs.readFileSync(enginePath, "utf8") + "\n;globalThis.E={runChecks};", ctx);
const DOC = (body) => `rules_version = '2';\nservice cloud.firestore {\n  match /databases/{database}/documents {\n${body}\n  }\n}\n`;
const WHOLE = (allow) => DOC(`    match /{document=**} {\n      ${allow}\n    }`);
const STO = (body) => `rules_version = '2';\nservice firebase.storage {\n  match /b/{bucket}/o {\n    match /{allPaths=**} {\n      ${body}\n    }\n  }\n}\n`;
const FB_PKG = '{"name":"x","dependencies":{"firebase":"^11.0.0"}}';
const rules = (name, text, extra = {}) => ({ files: [{ rel: name, name }, { rel: "package.json", name: "package.json" }], texts: new Map([[name, text], ["package.json", FB_PKG]]), gitignore: null, ...extra });
const proj = (files, extra = {}) => ({ files: Object.keys(files).map((rel) => ({ rel, name: rel.split("/").pop() })), texts: new Map(Object.entries(files)), gitignore: null, ...extra });
const CASES = {
  "01": rules("firestore.rules", WHOLE("allow read, write;")),
  "02": rules("firestore.rules", WHOLE("allow read, write: if request.auth.uid != null;")),
  "03": rules("firestore.rules", WHOLE("allow read, write: if request.auth != null || true;")),
  "04": rules("firestore.rules", WHOLE("allow read, write: if\n        request.auth != null;")),
  "05": rules("firestore.rules", WHOLE("allow read, write: if\n        true;")),
  "06": rules("firestore.rules", WHOLE("allow read, write: if (request.auth != null);")),
  "07": rules("firestore.rules", WHOLE("/* allow read, write: if true; */")),
  "08": rules("firestore.rules", DOC("    match /users/{userId} {\n      allow read, write: if request.auth != null && request.auth.uid == userId;\n    }")),
  "09": rules("storage.rules", STO("allow read;\n      allow write: if request.auth != null;")),
  "10": rules("database.rules.json", '{"rules":{".read":"now < 1767225600000",".write":false}}'),
  "11": rules("database.rules.json", '{"rules":{".read":"auth != null",".write":"auth != null"}}'),
  "12": rules("firestore.rules", DOC("    match /{document=**} { allow read, write: if true; }")),
  "13": rules("firestore.rules", WHOLE("allow read, write: if request.time < timestamp.date(2020, 1, 1);")),
  "14": rules("firestore.rules", WHOLE("allow read, write: if request.time < timestamp.date(2099, 1, 1);")),
  "15": rules("firestore.rules", WHOLE("allow read, write: if isSignedIn();")),
  "16": proj({ "firebase.json": '{"hosting":{"public":"dist"}}' }),
  "17": proj({ ".env": "X=1\n", ".gitignore": ".env*\n" }, { gitignore: ".env*\n" }),
  "18": proj({ ".env": "X=1\n" }, { envStatus: new Map([[".env", "tracked"]]) }),
  "19": proj({ ".env": `VITE_OPENAI_API_KEY=${J("sk-", "proj-", "FAKE".repeat(8), "0000")}\n`, "package.json": FB_PKG }),
  "20": proj({ "dist/assets/index.js": `const k="${J("sk_", "live_", "FAKE".repeat(4), "0000")}";\n`, "package.json": FB_PKG }),
  "21": proj({ "src/fb.ts": `const c = { apiKey: "${J("AIza", "SyFAKEFAKEFAKEFAKEFAKE_12345-abc")}", authDomain: "d.firebaseapp.com" };\n`, "package.json": FB_PKG }),
  "22": rules("firestore.rules", DOC("    match /posts/{id} {\n      allow get: if true;\n    }")),
  "23": proj({ "src/index.js": "console.log(1)\n", "package.json": '{"name":"c","dependencies":{"react":"^19"}}' }),
  "24": rules("firestore.rules", DOC("    match /posts/{postId} {\n      allow read: if true;\n    }")),
};
for (const [id, P] of Object.entries(CASES).sort(([a], [b]) => a.localeCompare(b))) {
  if (only && id !== only) continue;
  const R = ctx.E.runChecks(P);
  const out = ["danger", "warn", "info"].flatMap((k) => R.findings[k].map((f) => `${k}: ${f.title}` + (f.evidence ? "  ← " + f.evidence.map((e) => (e.loc && e.code != null ? `${e.loc} ${e.code}` : e.loc ? e.loc + (e.note || "") : e.note)).join(" | ") : "")));
  console.log(`#${id}  ${out.length ? out.join("\n     ") : "(何も出ない)"}`);
}
