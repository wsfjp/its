#!/usr/bin/env bash
# its_watch が接続する Chrome を、専用プロファイル・ポート 9222 で起動する（Windows Git Bash / Mac）
set -eu
for chrome in \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
  if [ -x "$chrome" ]; then
    profile="${USERPROFILE:-$HOME}/its-chrome"
    # Chrome が出し続けるログ（更新確認のエラーなど）は動作に関係ないので捨てる
    "$chrome" --remote-debugging-port=9222 --user-data-dir="$profile" > /dev/null 2>&1 &
    echo "Chrome を起動しました（プロファイル: $profile）"
    exit 0
  fi
done
echo "Chrome が見つかりません" >&2
exit 1
