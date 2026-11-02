# 追加観測（Claude Code）

`observe.py` は公式 command hook / statusLine の標準入力をローカルに記録する受動収集器です。Python 3標準ライブラリのみ、ネット通信・追加AI呼出・常駐監視なし。常用設定の自動変更はしません。既存の `collect.mjs`（Claude/Codex/Antigravityの過去ログ集計）はそのまま使えます。

## 収集と導入

1. `python3 observe.py config --dir /absolute/private-observations --settings /absolute/settings.json` で設定断片を生成します。`--base-settings /absolute/existing-settings.json` を付けると既存hookを保持した全体候補を標準出力に生成します。既存statusLineがある場合は拒否します。候補には既存設定の秘密が含まれ得るため、チャット・Git・公開場所へ出さないでください。
2. 差分を確認して、対象のClaude設定に追加します。共有の常用設定への反映はその環境の承認・競合確認に従います。設定を書き換えただけで、既存Claudeへ適用されたとはしません。公式のhook確認・必要な再開後、自然発火の記録で確認します。
3. `python3 observe.py export --dir /absolute/private-observations --out /absolute/private-export.json` で書き出し、LOGMAPの「観測ファイルを開く」で表示します。出力は既存ファイルを上書きしません。画面の上側のログ集計とは独立した観測パネルです。
4. 解除時は生成された4イベントのcommand hookとLOGMAPのstatusLineだけを取り除きます。既存hookや他設定は保持します。収集ファイルは自動削除しません。

出力ディレクトリは実パス（symlink不可）・本人所有0700、記録と鍵は0600。収集とexport全体を共通flockで直列化し、未完了ファイルの作成/読取/削除の競合も防ぎ、session IDはローカル鍵によるHMAC別名になります。`.key`を失うと以降の会話別名が変わります。同一OSユーザーからの改ざんを防ぐ権限分離ではありません。設定は明示指定のファイルだけ読み、payload内のcwdやfile_pathを読み先に使いません。

## 観測できるものと限界

- SessionStartのstartup/resume/clear/compact/fork、SessionEnd、ConfigChange、PostCompact。イベントの観測時刻でありOSプロセス再起動の証明ではありません。resumeは同一プロセス内にも発生します。
- 指定した設定ファイルのSHA256・model/effortLevel/autoCompactWindowのみ。ファイルに書かれた値であり、優先順位を解決した実効設定ではありません。
- statusLineが渡すmodel.id、effort.level、version、文脈内入力・直近応答出力・文脈枠、API換算推定額、5時間/週間の枠消費率とリセット時刻。提供されなかったフィールドは未取得、0ではありません。実料金・節約額ではありません。
- 利用率差は同じリセット時刻かつ単調な記録2点以上だけ。リセット跨ぎ・減少・同時刻矛盾は計算しません。別端末・並行作業を含むアカウント単位で、特定作業に帰属できません。パネル内の期間指定で1つの窓を選べます。
- 1日50MB、export最大100000件、入力1MB。収集前にpending記録を同期保存し、完了時だけ取り除きます。失敗・中断のpendingはexportに欠測として入り、その間の率差を止めます。保存先自体への書込み不可・hook未起動の空白は記録できないため、両端の観測差であって連続収集の証明ではありません。失敗時はpayloadを含まない警告をstderrに出し、hook/statusはexit0で本来の作業を止めません。記録が欠けた区間は収集成功扱いにしません。
- 時刻はこのMacの時計に依存します。署名・第三者証明はありません。会話本文・コード・元パスを出力しませんが、時刻・モデル・使用量は私的活動情報なので公開しないでください。
- Codex/Antigravityの追加起動観測は未対応。autoCompactWindowの実効値、実際の課金額、同一品質の仕事あたり節約量は別の証拠が必要です。

公式資料: https://code.claude.com/docs/en/hooks / https://code.claude.com/docs/en/statusline
