"""start-chrome.sh で起動した Chrome に接続し、Enter を押すたびに表示中の画面を保存する。

ブラウザの「名前を付けて保存」が使えない画面（フォーム送信後など）の取得用。
  python -m its_watch.snap
"""
import sys
import tomllib

from playwright.sync_api import sync_playwright

from .__main__ import save_capture


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    with open("config.toml", "rb") as f:
        cdp_url = tomllib.load(f)["browser"].get("cdp_url") or "http://localhost:9222"
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
        except Exception:
            print(f"Chrome に接続できません（{cdp_url}）。先に ./start-chrome.sh を実行してください")
            return 1
        n = 0
        while True:
            try:
                label = input("Enter で保存（メモを入力すると名前に付く / q で終了）> ").strip()
            except EOFError:
                break
            if label == "q":
                break
            # ITS のタブのうち最後に開かれたものを保存する
            pages = [pg for c in browser.contexts for pg in c.pages if "its-kenpo" in pg.url]
            if not pages:
                print("ITS のページが開かれていません")
                continue
            n += 1
            save_capture(pages[-1], f"snap{n:02d}" + (f"_{label}" if label else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
