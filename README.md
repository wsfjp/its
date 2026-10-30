# its-watch

ITS健保（関東ITソフトウェア健康保険組合）の保養施設について、空き照会を半自動化するツールです。

- Cloudflare Turnstile（ボット判定）は **人が通過させます**。スクリプトはその完了を待ち、以降の操作を自動で行います。
- アクセス遮断を避けるため、再読み込み間隔は 180 秒未満にできません。
- サイトの構造は [docs/site-research.md](docs/site-research.md) にまとめています。

## 現在の段階（Step 2: 複数施設の空き検索）

1. 入口の施設（`entry_apply_id`）の申込画面を開く。Turnstile の画面なら LINE で知らせ、人が通過させるのを待つ。
2. 申込画面の「空き状況カレンダー」を開く。カレンダーには全施設のタブがある。
3. `config.toml` の施設ごとに、対象期間の各月をカレンダー上で読み込み、条件（曜日・期間）に合う空き（○空き・△残りわずか）を集める。
   月を 1 つ読み込むごとに `request_wait_ms` だけ待つ。
4. 施設の優先順 → 曜日の優先順 → 日付の順に並べて LINE に送る。前回と同じ内容なら送らない。
5. `interval_sec` ごとに 3〜4 を繰り返す。セッションが切れて Turnstile に戻ったら LINE で知らせて終了する。

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

開いている Chrome をすべて閉じてから、付属のスクリプトで起動します（Windows の Git Bash / Mac）。
Chrome が出すログは捨てているので、ターミナルにエラーが流れ続けることはありません。

```bash
./start-chrome.sh
```

そのうえで `config.toml` の `cdp_url = "http://localhost:9222"` を設定して実行します。

## 今後の予定

1. 空き照会（Step 1: 画面の取得とセッション継続時間の計測）
2. 条件（施設・曜日・期間）に基づく空き検索と LINE 通知 ← 今ここ（カレンダーの読み取りは実画面で要確認）
3. 条件に合う枠の仮予約（30 分で失効）
4. 本予約
5. 毎月 27 日 0 時の解禁直後の検索と仮予約
