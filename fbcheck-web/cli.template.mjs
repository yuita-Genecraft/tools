#!/usr/bin/env node
/**
 * fbcheck — Firebase 公開前チェック（日本語）
 *
 * AIに作ってもらったアプリを公開する前に、実際に漏れた事例と同じ形の穴が
 * 空いていないかを、自分の目で確認できる形で出します。
 *
 * 使い方:  node fbcheck.mjs [プロジェクトのパス]
 * 依存なし。ネットワークに出ません。あなたのPCの中のファイルしか読みません。
 * 判定の本体（ENGINE の区間）は、ブラウザ版と同じ文字列です。
 */

import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

/* ENGINE */

const ROOT = path.resolve(process.argv[2] || ".");

// ---------- ファイル走査 ----------

function walk(dir, out = []) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (SKIP_DIRS.has(e.name)) continue;
      walk(p, out);
    } else if (e.isFile()) {
      const isEnv = e.name.startsWith(".env");
      if (!TEXT_EXT.has(extOf(e.name)) && !isEnv) continue;
      let st;
      try {
        st = fs.statSync(p);
      } catch {
        continue;
      }
      if (st.size > MAX_BYTES) continue;
      out.push(p);
    }
  }
  return out;
}

const read = (p) => {
  try {
    return fs.readFileSync(p, "utf8");
  } catch {
    return null;
  }
};
const toRel = (p) => (path.relative(ROOT, p) || path.basename(p)).split(path.sep).join("/");

// .env が Git で追跡されているか・除外されているかを、git 自身に確かめさせる。
// git が無い／git リポジトリの外なら null（＝判定は「未確認」になる）。ネットワークには出ない。
function gitEnvStatus(rels) {
  // ls-files はパスを glob として読まないよう --literal-pathspecs を付ける（check-ignore はこの指定を受け付けない）
  const git = (args, pre = []) => execFileSync("git", [...pre, "-C", ROOT, ...args], { stdio: ["ignore", "pipe", "ignore"] });
  try { if (String(git(["rev-parse", "--is-inside-work-tree"])).trim() !== "true") return null; } catch { return null; }
  const out = new Map();
  for (const rel of rels) {
    let st = "unknown";
    try { git(["ls-files", "--error-unmatch", "--", rel], ["--literal-pathspecs"]); st = "tracked"; }
    catch (e) {
      if (e.status === 1) {
        try { git(["check-ignore", "-q", "--", rel]); st = "untracked_ignored"; }
        catch (e2) { st = e2.status === 1 ? "untracked_not_ignored" : "unknown"; }
      }
    }
    out.set(rel, st);
  }
  return out;
}

// ---------- 出力 ----------

function box(label) {
  return `\n${label}\n${"─".repeat(46)}`;
}

function printFinding(f, i) {
  console.log(`\n${i + 1}. ${f.title}`);
  if (f.evidence?.length) {
    console.log("\n   根拠（あなたのファイルの実物）:");
    for (const e of f.evidence.slice(0, 8)) console.log(`     ${evText(e)}`);
    if (f.evidence.length > 8) console.log(`     …ほか ${f.evidence.length - 8} 件`);
  }
  const whyLabel = f.kind === "info" ? "   なぜそう言えるか:" : "   なぜ危ないか:";
  const howLabel = f.kind === "info" ? "   やること:" : "   直し方:";
  if (f.why) console.log(`\n${whyLabel}\n     ${f.why.split("\n").join("\n     ")}`);
  if (f.how) console.log(`\n${howLabel}\n     ${f.how.split("\n").join("\n     ")}`);
}

function main() {
  if (!fs.existsSync(ROOT)) {
    console.error(`パスが見つかりません: ${ROOT}`);
    process.exit(2);
  }

  console.log(`🔥 Firebase 公開前チェック  fbcheck v${FBCHECK_VERSION}`);
  console.log(`対象: ${ROOT}`);
  console.log("（このツールはネットに出ません。あなたのPCの中のファイルだけを読みます）");

  const files = walk(ROOT)
    .map((p) => ({ rel: toRel(p), name: path.basename(p), abs: p }))
    .sort((a, b) => (a.rel < b.rel ? -1 : a.rel > b.rel ? 1 : 0));
  console.log(`読んだファイル: ${files.length} 件`);

  const envStatus = gitEnvStatus(files.filter((f) => f.name.startsWith(".env") && !TEMPLATE_ENV.test(f.name)).map((f) => f.rel));
  console.log(envStatus ? "Git：.env の追跡と除外を git 自身で確かめます" : "Git：git が無いか git リポジトリの外なので、.env が追跡済みかは確かめられません");
  const res = runChecks({
    files: files.map(({ rel, name }) => ({ rel, name })),
    texts: new Map(files.map((f) => [f.rel, read(f.abs)])),
    gitignore: read(path.join(ROOT, ".gitignore")),
    envStatus,
  });
  if (res.fb.length) {
    console.log(`Firebase を検出: ${res.fb.slice(0, 3).join(" / ")}`);
  } else {
    console.log("Firebase は見つかりませんでした → ルールの確認は飛ばして、鍵まわりだけ見ます");
  }

  const { danger, warn, info, ok } = res.findings;

  if (danger.length) {
    console.log(box(`■ 公開前に直すもの（${danger.length}件）`));
    danger.forEach(printFinding);
  }
  if (warn.length) {
    console.log(box(`■ 見ておくもの（${warn.length}件）`));
    warn.forEach(printFinding);
  }
  if (info.length) {
    console.log(box("■ 直さなくていいもの（よくある誤解）"));
    info.forEach(printFinding);
  }
  if (ok.length) {
    console.log(box("■ 問題なし"));
    ok.forEach((f) => console.log(`  ・${f.title}`));
  }

  console.log(box("■ 結果"));
  if (danger.length === 0 && warn.length === 0) {
    console.log("  この4項目については、危ない状態は見つかりませんでした。");
  } else {
    console.log(`  公開前に直すもの: ${danger.length}件 / 見ておくもの: ${warn.length}件`);
  }
  if (!res.fb.length) {
    console.log("  ※ このプロジェクトでは Firebase が見つからなかったので、ルールの項目は判定していません。");
  }
  console.log(
    "\n  このツールが見ているのは、実際の漏洩でよく見られる4か所だけです。\n" +
    "  ここが通っても、全部が安全という意味ではありません。\n" +
    "  逆に、ここが赤い場合は、実際に漏れた事例と同じ形になっています。"
  );
  console.log("");

  process.exit(danger.length ? 1 : 0);
}

main();
