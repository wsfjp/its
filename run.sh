#!/usr/bin/env bash
# 空き検索（と設定に応じた仮予約）を 1 回実行する。
# 前回の Chrome（its-chrome プロファイル、ポート 9222）が残っていれば閉じ、起動し直してから実行する。
# 実行後の Chrome は、続きの手作業ができるよう開いたままにする（次回の実行時に閉じる）。
#   ./run.sh            通常の実行
#   ./run.sh --save     カレンダー画面も captures/ に保存する
set -eu
cd "$(dirname "$0")"
CDP_URL="http://localhost:9222"

# 仮想環境があれば使う（Windows の Git Bash / Mac・Linux）
if [ -f .venv/Scripts/activate ]; then
  source .venv/Scripts/activate
elif [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi
PYTHON=python
command -v python > /dev/null 2>&1 || PYTHON=python3

cdp_up() { curl -s -o /dev/null --max-time 2 "$CDP_URL/json/version"; }

# 前回の Chrome が残っていれば閉じる
if cdp_up; then
  echo "前回の Chrome を閉じます"
  "$PYTHON" - "$CDP_URL" <<'PY' || true
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(sys.argv[1])
    try:
        browser.new_browser_cdp_session().send("Browser.close")
    except Exception:
        pass  # 閉じると同時に接続も切れる
PY
  for _ in $(seq 1 20); do cdp_up || break; sleep 0.5; done
  if cdp_up; then
    echo "Chrome を閉じられませんでした。Chrome のウィンドウを閉じてから再実行してください" >&2
    exit 1
  fi
fi

./start-chrome.sh

# Chrome が接続を受け付けるまで待つ
for _ in $(seq 1 30); do cdp_up && break; sleep 0.5; done
if ! cdp_up; then
  echo "Chrome が起動しませんでした。開いている Chrome をすべて閉じてから再実行してください" >&2
  exit 1
fi

"$PYTHON" -m its_watch "$@"
