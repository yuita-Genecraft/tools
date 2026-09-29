# tools — ブラウザだけで動く道具

AIで開発する人向けの、ページの中だけで動く小さな道具です。外部APIを使わず、あなたのファイルを外に送りません（ページ側の CSP で通信そのものを禁止しています）。

| 道具 | 中身 | ソース |
|---|---|---|
| Claude Code 通知表 | `~/.claude/projects` のログを集計し、口ぐせ・謝られた回数・作業時間・APIトークン料金の換算・称号を通知表の画像にする | `cc-tsuchihyo/app.html` |
| Firebase 公開前チェック | [fbcheck](https://github.com/yuita-Genecraft/fbcheck)（Node版）と同じ判定をブラウザで。フォルダをドロップするだけ | `fbcheck-web/app.html` |

## 仕組み

- `*/app.html` は claude.ai の Artifact 用（doctype などの骨格なし）
- `build_standalone.py` で doctype・CSP・OGP を付けた単体の HTML にする
- `build_site.py <公開先URL>` で GitHub Pages 用の `docs/` を作る
- X などのカード画像は `docs/og/*.png`。`og/*.html` を `render_og.py` で撮って作る（通知表のカードは、アプリの見本をその場で描いて使う）
- CSP は `default-src 'none'; connect-src 'none'` ほか。fetch / XHR / WebSocket はブラウザが止める

## テスト

- 通知表：`test/gen.py`（境界ケース入りの合成ログ）→ `test/ref.py`（Python で書いた別実装）→ `test/e2e.py`（Chromium で開いて集計値を突き合わせ）
- 公開前チェック：判定の本体は `fbcheck-web/engine.js`。`fbcheck-web/sync_engine.py <出力先>` で、ブラウザ版と CLI（`fbcheck.mjs`）に同じ文字列で入れる
  - `test/e2e_fb.py`：テスト用プロジェクト8種（`test/gen_fbproj.py` が作る）。git の外の5種はブラウザ版と CLI の結果が一致するか、本物の git リポジトリの3種は CLI が git の答えどおりに出すか・ブラウザ版が「未確認」で出すか。あわせて言い過ぎ・偽PASSが出ないか
  - `test/unit_engine.mjs`：.gitignore の読み・ルールの読み・文言（言い過ぎ）の単体テスト
  - `test/gitcheck.mjs`：自前の .gitignore 読み取り（補助）を本物の `git check-ignore` と突き合わせる。範囲は「直下の .gitignore × 未追跡のファイル」だけ。追跡済みのファイルや下の階層の .gitignore はこの範囲の外なので、CLI は git 自身で確かめ、ブラウザ版は「未確認」と出す
- 動かし方：`node test/unit_engine.mjs`・`node test/gitcheck.mjs`・`python3 test/e2e_fb.py`・`python3 test/e2e.py`（e2e は Playwright の Chromium を使う。CLI は `test/out/` に毎回作る）

## 集計で気をつけたこと（通知表）

- Claude Code のログは、1つの応答をブロックごとに別の行へ書き、同じ `usage` を行ごとに繰り返す。`message.id` + `requestId` で1回に畳まないと、トークン料金の換算が数倍に膨らむ
- 再開したセッションは前の行を同じ `uuid` で写すことがあるので、`uuid` でも重複を除く
- 料金表は 2026-09-29 時点の [公開料金](https://platform.claude.com/docs/en/about-claude/pricing)。料金表に無いモデルは同じ系列の最新単価で計算し「推定」と表示する

## 公開

GitHub Pages：Settings → Pages → Source を「Deploy from a branch」にして、Branch: `main` / `/docs` を選ぶ。公開先は `https://yuita-genecraft.github.io/tools/`（`build_site.py` の既定値。リポジトリ名を変えたら引数で渡す）。

個人が作った非公式の道具です。Anthropic、Google とは関係ありません。MIT License.
