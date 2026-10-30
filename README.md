# its-watch

ITS健保（関東ITソフトウェア健康保険組合）の保養施設について、空き照会を半自動化するツールです。

- Cloudflare Turnstile（ボット判定）は **人が通過させます**。スクリプトはその完了を待ち、以降の操作を自動で行います。
- アクセス遮断を避けるため、再読み込み間隔は 180 秒未満にできません。
- サイトの構造は [docs/site-research.md](docs/site-research.md) にまとめています。

## 現在の段階（Step 2）

1. 指定施設の空き照会ページを開く。Turnstile の画面なら LINE で知らせ、人が通過させるのを待つ。
2. 通過後の申込画面を `captures/` に保存する（初回のみ）。
3. 「希望日」プルダウン（空きのある日だけが並ぶ）を読み取り、`config.toml` の条件（曜日・期間）で絞り込む。
4. **前回の確認以降に新しく空いた日だけ** LINE に通知する。前回の結果は `state.json` に保存される。
5. 一定間隔で再読み込みして 3〜4 を繰り返す。セッションが切れて Turnstile に戻ったら LINE で知らせて終了する。

`state.json` を削除すると、次回は条件に合う空き日をすべて通知します。

## セットアップ（自分の PC）

Python 3.11 以上が必要です。Windows では `python3` ではなく `python`（または `py`）を使ってください。

```bash
python -m venv .venv
```

仮想環境の有効化（Mac / Linux）:

```bash
source .venv/bin/activate
```

仮想環境の有効化（Windows の Git Bash）:

```bash
source .venv/Scripts/activate
```

```bash
pip install -r requirements.txt
```

`playwright` コマンドに PATH が通っていなくても動くよう、`python -m` 経由で実行します。

```bash
python -m playwright install chromium
```

```bash
cp config.example.toml config.toml
```

```bash
cp .env.example .env
```

## LINE 通知の設定（Messaging API）

LINE Notify は 2025 年 3 月で終了したため、Messaging API を使います。無料枠は月 200 通です。

1. [LINE Developers](https://developers.line.biz/console/) にログインし、プロバイダーを作成する。
2. 画面の案内に従って LINE 公式アカウントを作成し、Messaging API を有効にする。
3. チャネルの「Messaging API 設定」タブで **チャネルアクセストークン（長期）** を発行し、`.env` の `LINE_CHANNEL_ACCESS_TOKEN` に設定する。
4. 「チャネル基本設定」タブにある **あなたのユーザー ID**（`U` で始まる文字列）を `.env` の `LINE_TO_USER_ID` に設定する。
5. 「Messaging API 設定」タブの QR コードから、その公式アカウントを LINE で友だち追加する。
6. 次のコマンドで、テストメッセージが届くことを確認する。

```bash
python -m its_watch --test-line
```

`.env` はトークンを含むため git 管理外にしています。

## 実行

```bash
python -m its_watch
```

ブラウザが開いて Turnstile の画面になったら、チェックを入れて「次へ」を押してください。

### Turnstile がうまく通らない場合

スクリプトが起動したブラウザではなく、普段使っている Chrome を別プロファイルで起動して接続できます。

Mac の場合:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/its-chrome"
```

Windows（PowerShell）の場合:

```bash
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:USERPROFILE\its-chrome"
```

そのうえで `config.toml` の `cdp_url = "http://localhost:9222"` を設定して実行します。

## 今後の予定

1. 空き照会（Step 1: 画面の取得とセッション継続時間の計測）
2. 条件（施設・曜日・期間）に基づく空き検索と LINE 通知 ← 今ここ
3. 条件に合う枠の仮予約（30 分で失効）
4. 本予約
5. 毎月 27 日 0 時の解禁直後の検索と仮予約
