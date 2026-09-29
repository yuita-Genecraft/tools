// gitignoreCovers が「除外されている」と言ったものは、本物の git でも必ず除外されているか（偽PASSが無いか）
import fs from "node:fs"; import os from "node:os"; import path from "node:path"; import vm from "node:vm"; import { execFileSync } from "node:child_process";
const src = fs.readFileSync(new URL("../fbcheck-web/engine.js", import.meta.url), "utf8");
const ctx = {}; vm.createContext(ctx); vm.runInContext(src + "\n;globalThis.E={gitignoreCovers};", ctx);
const pats = [".env", ".env*", "*.local", ".env*.local", "/.env", "**/.env", "apps/", "apps/web/.env", "web/.env", ".env/", "*", "*.env", ".env.*", "env", "/apps/**/.env*", ".env\n!.env", ".env*\n!.env.production", ".env*\n!.env.example", "[.]env", "\\.env", ".env?local", "apps/**", "**/web/", ".env.production", "!.env\n.env"];
const files = [".env", ".env.production", ".env.local", ".env.production.local", "apps/web/.env", "apps/web/.env.local", "config/.env", "web/.env", "prod.env"];
let falsePass = 0, conservative = 0, same = 0;
for (const pat of pats) for (const f of files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gi-"));
  execFileSync("git", ["init", "-q"], { cwd: dir });
  fs.writeFileSync(path.join(dir, ".gitignore"), pat + "\n");
  fs.mkdirSync(path.dirname(path.join(dir, f)), { recursive: true }); fs.writeFileSync(path.join(dir, f), "x");
  let git; try { execFileSync("git", ["check-ignore", "-q", f], { cwd: dir }); git = true; } catch { git = false; }
  const mine = ctx.E.gitignoreCovers(pat + "\n", f).covered;
  if (mine && !git) { falsePass++; console.log("FALSE PASS:", JSON.stringify(pat), f); }
  else if (!mine && git) conservative++;
  else same++;
  fs.rmSync(dir, { recursive: true, force: true });
}
console.log(`cases=${pats.length * files.length} same=${same} conservative(安全側に外した)=${conservative} falsePass=${falsePass}`);
process.exit(falsePass ? 1 : 0);
