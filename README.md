# its-watch

ITS健保（関東ITソフトウェア健康保険組合）の保養施設について、空き照会を半自動化するツールです。

- Cloudflare Turnstile（ボット判定）は **人が通過させます**。スクリプトはその完了を待ち、以降の操作を自動で行います。
- アクセス遮断を避けるため、再読み込み間隔は 180 秒未満にできません。
- サイトの構造は [docs/site-research.md](docs/site-research.md) にまとめています。

## 空き検索の流れ

1. ITS ホームページの施設紹介「空き状況確認」タブ（`public_url`）を開き、埋め込まれた予約システムの「空き状況確認」を押して、全施設のタブがある「空き状況カレンダー」を開く。
   この入口には Turnstile がない。`entry = "apply"` にすると、申込画面（Turnstile あり）から開く従来の方法になる。
2. `config.toml` の施設ごとに、対象期間の各月をカレンダー上で読み込み、条件（曜日・期間）に合う空き（○空き・△残りわずか）を集める。
   月を 1 つ読み込むごとに `request_wait_ms` だけ待つ。
3. 施設の優先順 → 曜日の優先順 → 日付の順に並べて LINE に送る。前回と同じ内容なら送らない。
4. 既定では 1 回確認して終了する。`max_rounds` を増やすと `interval_sec` ごとに 1〜3 を繰り返すが、カレンダーを開くたびに Turnstile が出ることがある。

## 仮予約（Step 3）

`config.toml` の `[reserve] mode` で動作を切り替えます。

| mode | 動作 |
|---|---|
| `off` | 仮予約しない（空きの通知のみ） |
| `dry_run` | 条件に合う最優先の枠で、申込画面に希望日・一泊・人数・部屋数 1 を入れて「空き検索」し、人数が収まる最小定員の部屋にチェックを入れて止める。「予約手続きに進む」は押さないので部屋は確保されない |
| `submit` | さらに「予約手続きに進む」→「同意する」→ メールアドレス（`.env` の `ITS_EMAIL`）を送信する。30 分で失効する仮予約になる。`confirm = true` なら送信前にターミナルで y/N を確認する |

仮予約後は、届いたメール（件名「○○申込手続きのご案内」、noreply@mail.its-kenpo.or.jp から）の
`https://as.its-kenpo.or.jp/apply/new?c=...` から、「予約手続きに進む」を押してから 30 分以内に手作業で手続きを完了してください。
仮予約では施設の申込画面を開くため Turnstile が出ます。LINE で知らせるので、人が通過させてください。
スクリプトが Chrome に接続したままだと Turnstile の判定に失敗するため、Turnstile の間は接続を切り、申込画面に進んだのを確認してから接続し直します。

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

Chrome の起動から空き検索（`mode` に応じて仮予約）までを、次の 1 コマンドで行います。
前回の Chrome が残っていれば閉じてから起動し直します。実行後の Chrome は、続きを手作業で行えるよう開いたままにします。

```bash
./run.sh
```

Chrome を自分で起動してスクリプトだけ実行する場合は、次のとおりです。

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
2. 条件（施設・曜日・期間）に基づく空き検索と LINE 通知
3. 条件に合う枠の仮予約（30 分で失効）。記号番号・メールアドレスを入力して送信するまで。
   `dry_run` で送信直前に止めるモードを用意する（動作確認済み）
4. 本予約（当面は手作業）
5. 毎月 27 日 0 時の解禁直後の検索と仮予約
