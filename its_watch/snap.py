"""start-chrome.sh で起動した Chrome に、Enter を押した瞬間だけ接続して表示中の画面を保存する。

接続したままだと Turnstile に人間ではないと判定されるため、保存のたびに接続・切断する。
ブラウザの「名前を付けて保存」が使えない画面（フォーム送信後など）の取得用。
Turnstile の画面が出ている間は使わないこと。
  python -m its_watch.snap
"""
import sys
import tomllib

from playwright.sync_api import sync_playwright

from .__main__ import save_capture


def snap(cdp_url: str, label: str) -> None:
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
        except Exception:
            print(f"Chrome に接続できません（{cdp_url}）。先に ./start-chrome.sh を実行してください")
            return
        # ITS のタブのうち最後に開かれたものを保存する
        pages = [pg for c in browser.contexts for pg in c.pages if "its-kenpo" in pg.url]
        if pages:
            save_capture(pages[-1], label)
        else:
            print("ITS のページが開かれていません")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    with open("config.toml", "rb") as f:
        cdp_url = tomllib.load(f)["browser"].get("cdp_url") or "http://localhost:9222"
    n = 0
    while True:
        try:
            label = input("Enter で保存（メモを入力すると名前に付く / q で終了）> ").strip()
        except EOFError:
            break
        if label == "q":
            break
        n += 1
        snap(cdp_url, f"snap{n:02d}" + (f"_{label}" if label else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
