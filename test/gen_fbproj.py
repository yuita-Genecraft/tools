#!/usr/bin/env python3
"""Firebase 公開前チェックのテスト用プロジェクト（fbproj / fbproj2 / fbproj3）を作る。
偽の鍵は実在の形式に近いので、ソースに連続した文字列として置かず、実行時に組み立てる。"""
import json, pathlib, shutil, subprocess
HERE = pathlib.Path(__file__).parent
J = "".join
FAKE_OPENAI = J(["sk-", "proj-", "FAKE" * 8, "0000"])
FAKE_OPENAI2 = J(["sk-", "proj-", "FAKE" * 8, "9999"])
FAKE_STRIPE = J(["sk_", "live_", "FAKE" * 4, "0000"])
FAKE_ANTHROPIC = J(["sk-", "ant-", "FAKE-" * 5, "0000"])
FAKE_FB_APIKEY = J(["AIza", "SyFAKEFAKEFAKEFAKEFAKE_12345-abc"])

def w(root, p, s):
    p = root / p; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")

def main():
    for n in ("fbproj", "fbproj2", "fbproj3", "fbproj4", "fbproj5", "fbproj6", "fbproj7", "fbproj8"):
        shutil.rmtree(HERE / n, ignore_errors=True)
    R = HERE / "fbproj"
    w(R, "firebase.json", json.dumps({"firestore": {"rules": "firestore.rules"}, "storage": {"rules": "storage.rules"}}, indent=2))
    w(R, "firestore.rules", "rules_version = '2';\nservice cloud.firestore {\n  match /databases/{database}/documents {\n    // 開発中にAIが書いたルール\n    match /public/{doc} {\n      allow read, write: if true;\n    }\n    match /users/{userId} {\n      allow read: if request.auth != null && request.auth.uid == userId;\n      match /posts/{postId} {\n        allow read, write: if request.auth != null;\n      }\n    }\n    match /{document=**} {\n      allow read, write: if request.time < timestamp.date(2099, 1, 1);\n    }\n  }\n}\n")
    w(R, "storage.rules", "rules_version = '2';\nservice firebase.storage {\n  match /b/{bucket}/o {\n    match /{allPaths=**} {\n      allow read, write: if request.time < timestamp.date(2024, 5, 1);\n    }\n  }\n}\n")
    w(R, "database.rules.json", json.dumps({"rules": {".read": True, ".write": False}}, indent=2))
    w(R, ".gitignore", "node_modules\ndist-old\n")
    w(R, ".env", f"NEXT_PUBLIC_SECRET_TOKEN=abc123\nOPENAI_API_KEY={FAKE_OPENAI}\nVITE_FIREBASE_API_KEY=AIzaFAKE\n")
    w(R, ".env.example", f"OPENAI_API_KEY={FAKE_OPENAI2}\n")
    w(R, "src/lib/firebase.ts", f'import {{ initializeApp }} from "firebase/app";\nconst firebaseConfig = {{\n  apiKey: "{FAKE_FB_APIKEY}",\n  authDomain: "demo.firebaseapp.com",\n}};\nexport const app = initializeApp(firebaseConfig);\n')
    w(R, "src/server.ts", f'const stripe = "{FAKE_STRIPE}";\n')
    w(R, "dist/assets/index-3f9a.js", f'var a=1;const k="{FAKE_ANTHROPIC}";fetch("/x",{{headers:{{k}}}});\n')
    w(R, "node_modules/pkg/index.js", f'const s="{FAKE_STRIPE}";\n')
    w(R, "package.json", json.dumps({"name": "demo", "dependencies": {"firebase": "^11.0.0"}}, indent=2))
    w(R, "public/big.js", "x" * (2 * 1024 * 1024 + 10) + f'\nconst s="{FAKE_STRIPE}";\n')
    w(R, "README.md", "# demo\n")
    R2 = HERE / "fbproj2"   # Firebase なし・問題なし
    w(R2, "src/index.js", 'console.log("hi")\n')
    w(R2, "package.json", '{"name":"clean","dependencies":{"react":"^19"}}\n')
    w(R2, ".gitignore", ".env*\nnode_modules\n")
    w(R2, ".env", "API_KEY=x\n")
    R3 = HERE / "fbproj3"   # Firebase あり・ルールファイルなし
    w(R3, "firebase.json", '{"hosting":{"public":"dist"}}\n')
    w(R3, "src/app.js", 'import { initializeApp } from "firebase/app";\n')
    R4 = HERE / "fbproj4"   # セカンドオピニオンの指摘を再現する形
    w(R4, "firebase.json", '{"firestore":{"rules":"firestore.rules"}}\n')
    w(R4, "package.json", '{"name":"r4","dependencies":{"firebase":"^11.0.0"}}\n')
    w(R4, ".gitignore", ".env\n")                       # .env だけ → .env.production は除外されない
    w(R4, ".env", f"OPENAI_API_KEY={FAKE_OPENAI}\n")
    w(R4, ".env.production", "API_URL=https://example.com\n")
    w(R4, ".env.local", f"VITE_OPENAI_API_KEY={FAKE_OPENAI}\n")   # 接頭辞つきの変数に本物らしき鍵
    w(R4, "firestore.rules", """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /posts/{postId} {
      allow read: if true;
    }
    match /announcements/{id} {
      allow read: if request.auth != null;
    }
    match /events/{eventId} {
      allow create: if request.resource.data.date > timestamp.date(2020, 1, 1);
    }
    match /logs/{id} { allow write: if request.time < timestamp.date(2099, 1, 1); }
  }
}
""")
    R5 = HERE / "fbproj5"   # 全体に効く auth だけのルール・RTDB の一部公開・Storage 全体の読み取り
    w(R5, "firebase.json", '{"firestore":{"rules":"firestore.rules"}}\n')
    w(R5, "firestore.rules", """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.auth != null;
    }
  }
}
""")
    w(R5, "database.rules.json", '{"rules":{"public":{".read":true},"private":{".read":"auth != null"}}}\n')
    w(R5, "storage.rules", """rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /{allPaths=**} { allow read: if true; }
  }
}
""")
    w(R5, ".gitignore", ".env*\n!.env.example\n")
    w(R5, ".env.production", "X=1\n")
    w(R5, ".env.example", "OPENAI_API_KEY=\n")
    w(R5, "apps/web/.env", "Y=2\n")                    # 階層の下の .env も .env* で除外される
    # --- 本物の git リポジトリでしか起きない形（セカンドオピニオン再レビューの BLOCK）
    def git(root, *args):
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root, check=True, capture_output=True)
    R6 = HERE / "fbproj6"   # .env をコミットしてから、あとで .gitignore に .env* を足した
    w(R6, "package.json", '{"name":"r6"}\n')
    w(R6, ".env", f"OPENAI_API_KEY={FAKE_OPENAI}\n")
    git(R6, "init", "-q"); git(R6, "add", ".env", "package.json"); git(R6, "commit", "-q", "-m", "first")
    w(R6, ".gitignore", ".env*\n"); git(R6, "add", ".gitignore"); git(R6, "commit", "-q", "-m", "ignore env")
    R7 = HERE / "fbproj7"   # 直下は .env*、下の階層の .gitignore が !.env で打ち消す
    w(R7, "package.json", '{"name":"r7"}\n')
    w(R7, ".gitignore", ".env*\n")
    w(R7, "apps/web/.gitignore", "!.env\n")
    w(R7, "apps/web/.env", "API_URL=https://example.com\n")
    git(R7, "init", "-q"); git(R7, "add", ".gitignore", "apps/web/.gitignore", "package.json"); git(R7, "commit", "-q", "-m", "first")
    R8 = HERE / "fbproj8"   # 直下の .env* で、追跡していない .env（正しく除外されている）
    w(R8, "package.json", '{"name":"r8"}\n')
    w(R8, ".gitignore", ".env*\n")
    w(R8, ".env", "X=1\n")
    git(R8, "init", "-q"); git(R8, "add", ".gitignore", "package.json"); git(R8, "commit", "-q", "-m", "first")
    print("ok")

if __name__ == "__main__":
    main()
