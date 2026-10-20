# tools — ブラウザだけで動く道具

AIで開発する人向けの、ページの中だけで動く小さな道具です。外部APIを使わず、あなたのファイルを外に送りません（ページ側の CSP で通信そのものを禁止しています）。

| 道具 | 中身 | ソース |
|---|---|---|
| Claude Code 通知表 | `~/.claude/projects` のログを集計し、推定作業時間・使った日数・よく使ったツール・APIトークン料金の換算を通知表の画像にする（「ありがとう」などの回数と称号はおまけ） | `cc-tsuchihyo/app.html` |
| Firebase 公開前チェック | [fbcheck](https://github.com/yuita-Genecraft/fbcheck)（Node版）と同じ判定をブラウザで。フォルダをドロップするだけ | `fbcheck-web/app.html` |
| Claude Code 生存率 | `~/.claude/projects` のログと、手元のプロジェクトのフォルダを突き合わせて、Claude が書いた行のうち今も残っている割合を「残った・Claude が自分で書き直した・人が消した」に分けて1枚の画像にする。期間つきの AI率、人が消した行が多いファイルも | `cc-seizon/app.html` |

## 仕組み

- `*/app.html` は claude.ai の Artifact 用（doctype などの骨格なし）
- `build_standalone.py` で doctype・CSP・OGP を付けた単体の HTML にする
- `build_site.py <公開先URL>` で GitHub Pages 用の `docs/` を作る
- X などのカード画像は `docs/og/*.png`。`og/*.html` を `render_og.py` で撮って作る。通知表のカードは `--card` で渡した画像を使う（公開中の画像は作者の実際の通知表）。渡さない時は、アプリの見本をその場で描いて使う
- CSP は `default-src 'none'; connect-src 'none'` ほか。fetch / XHR / WebSocket はブラウザが止める

## テスト

- 通知表：`test/gen.py`（境界ケース入りの合成ログ）→ `test/ref.py`（Python で書いた別実装）→ `test/e2e.py`（Chromium で開いて集計値を突き合わせ）
- 生存率：`test/gen_seizon.py`（Edit／Write／MultiEdit・old 側に元からある行・Claude 自身の書き直し・人が直した行・ファイルごと消えた・失敗した Edit・結果の無い Write・再開で写った行・別プロジェクト・同名の別フォルダ・数えない行・空白違い・CRLF・鍵らしい行・読まないファイルを混ぜた合成ログとフォルダ）→ `test/ref_seizon.py`（Python の別実装）→ `test/e2e_seizon.py`（Chromium で2つのフォルダを入れ、通常と厳密の両モードで別実装と、手で数えた期待値の両方に突き合わせ）
- 公開前チェック：判定の本体は `fbcheck-web/engine.js`。`fbcheck-web/sync_engine.py <出力先>` で、ブラウザ版と CLI（`fbcheck.mjs`）に同じ文字列で入れる
  - `test/e2e_fb.py`：テスト用プロジェクト8種（`test/gen_fbproj.py` が作る）。git の外の5種はブラウザ版と CLI の結果が一致するか、本物の git リポジトリの3種は CLI が git の答えどおりに出すか・ブラウザ版が「未確認」で出すか。あわせて言い過ぎ・偽PASSが出ないか
  - `test/unit_engine.mjs`：.gitignore の読み・ルールの読み・文言（言い過ぎ）の単体テスト
  - `test/gitcheck.mjs`：自前の .gitignore 読み取り（補助）を本物の `git check-ignore` と突き合わせる。範囲は「直下の .gitignore × 未追跡のファイル」だけ。追跡済みのファイルや下の階層の .gitignore はこの範囲の外なので、CLI は git 自身で確かめ、ブラウザ版は「未確認」と出す
- 動かし方：`node test/unit_engine.mjs`・`node test/gitcheck.mjs`・`python3 test/e2e_fb.py`・`python3 test/e2e.py`・`python3 test/e2e_seizon.py`（e2e は Playwright の Chromium を使う。CLI は `test/out/` に毎回作る）

### 通知表の自動E2E

`main` 向けのPR（Draftを含む）の作成・更新・再オープン時に、GitHub Actions の `Notification report E2E` が通常の集計比較と重複時間テスト、生存率の突き合わせ（`test/e2e_seizon.py`）を実行します。Python 3.12 / Playwright 1.58.0 / Chromiumを使用し、入力はテストが生成する合成ログだけです。集計の不一致やテスト例外はジョブ失敗になります。通常の比較が失敗しても、ブラウザの準備が完了していれば重複時間テストも実行します。

実行結果はPRのChecksまたはActionsの各ステップのログで確認できます。デスクトップ・モバイルの見本画面の横はみ出し、収集したブラウザエラー・警告、Playwrightのrequestイベントで観測した外部リクエストも失敗判定に含みます。CSP有効の検証では見本画像のPNG読み込み完了を待ち、ブラウザエラーと外部リクエストを判定します（この検証のconsole警告は収集対象外）。`file:`・`data:`・`blob:`はローカル表示用として許可します。全画面状態や全通信経路の保証ではなく、Firebase公開前チェックのテストもこのワークフローの対象外です。

公開リポジトリの標準Ubuntuランナーでのみ実行し、非公開リポジトリではジョブをスキップします。追加の保存容量課金を避けるため、artifactアップロードとActionsキャッシュは使いません。スクリーンショットは実行中に生成されますが、ジョブ終了後には保存されません。ログはGitHubの保持設定に従います。このワークフローはdeploy・`docs/`更新・自動mergeを行いません。

ローカルで同じテストを実行する場合：

```sh
python -m pip install -r test/requirements-e2e.txt
python -m playwright install --with-deps chromium
python -u test/e2e.py
python -u test/test_overlap.py
```

## 集計で気をつけたこと（生存率）

- 「Claude が書いた行」＝Edit の new 側にあって old 側に無い行、Write は Read で見えていた行（と `toolUseResult.originalFile`）を除いた行。行は前後の空白を落として空白をそろえて比べ、4文字未満と記号だけの行は数えない（厳密モードで切り替え）
- 3分類＝今も同じ行で残っている／Claude が後の Edit の old 側か Write の書き換えで自分で消した／それ以外（人が消した・直した・ファイルごと消えた・Bash で消した）。人が少し直した行は「残った」に入らない＝下限の値
- ログの絶対パスと、落としたフォルダの相対パスを末尾で照合し、いちばん多く一致した場所を root にする。同じ名前のフォルダが別の場所にある時は一致の多い方
- 失敗した Edit（`is_error`）と、結果の記録が無い Edit／Write は適用しない。tool_use の id で重複を除く（再開したセッションは前の行を写す）
- ログは初期設定で30日より古いものが消えるので、AI率は必ず期間つきで出す。頭に置く数字は生存率

## 集計で気をつけたこと（通知表）

- Claude Code のログは、1つの応答をブロックごとに別の行へ書き、同じ `usage` を行ごとに繰り返す。`message.id` + `requestId` で1回に畳まないと、トークン料金の換算が数倍に膨らむ
- 再開したセッションは前の行を同じ `uuid` で写すことがあるので、`uuid` でも重複を除く
- 料金表は 2026-09-29 時点の [公開料金](https://platform.claude.com/docs/en/about-claude/pricing)。料金表に無いモデルは同じ系列の最新単価で計算し「推定」と表示する

## 公開

GitHub Pages：Settings → Pages → Source を「Deploy from a branch」にして、Branch: `main` / `/docs` を選ぶ。公開先は `https://yuita-genecraft.github.io/tools/`（`build_site.py` の既定値。リポジトリ名を変えたら引数で渡す）。

個人が作った非公式の道具です。Anthropic、Google とは関係ありません。MIT License.
