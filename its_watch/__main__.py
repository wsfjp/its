"""ITS健保 保養施設の空き照会（半自動）。

Turnstile は人が通過させ、それ以降の照会・通知を自動で行う。
"""
import argparse
import datetime as dt
import pathlib
import sys
import time
import tomllib

from playwright.sync_api import Page, sync_playwright

from .calendar import search_all
from .line import load_dotenv, notify
from .sitecodec import empty_apply_url

CAPTURE_DIR = pathlib.Path("captures")
MIN_INTERVAL_SEC = 180
MIN_REQUEST_WAIT_MS = 2000


def is_captcha_page(page: Page) -> bool:
    return "/apply/capture_check" in page.url or page.locator(".cf-turnstile").count() > 0


def save_capture(page: Page, label: str) -> pathlib.Path:
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = CAPTURE_DIR / f"{dt.datetime.now():%Y%m%d-%H%M%S}_{label}"
    stem.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(stem.with_suffix(".png")), full_page=True)
    print(f"保存: {stem}.html / .png  ({page.url})")
    return stem


def wait_for_human(page: Page, timeout_sec: int) -> bool:
    """Turnstile を人が通過して次の画面に進むまで待つ。"""
    print("\a")
    notify("【ITS】ブラウザで「確認」にチェックして「次へ」を押してください")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not is_captcha_page(page):
            return True
        page.wait_for_timeout(1000)
    return False


def open_calendar(page: Page, cfg: dict) -> Page | None:
    """申込画面に入り（Turnstile は人が通過）、「空き状況カレンダー」を開く。"""
    page.goto(empty_apply_url(cfg["entry_apply_id"]))
    if is_captcha_page(page) and not wait_for_human(page, cfg["captcha_timeout_sec"]):
        notify("【ITS】Turnstile 待ちがタイムアウトしました")
        return None
    page.wait_for_load_state("networkidle")
    with page.context.expect_page() as popup:
        page.click("#showStatus")
    cal = popup.value
    cal.wait_for_load_state("networkidle")
    return cal


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m its_watch")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--test-line", action="store_true", help="LINE 通知のテストだけ行う")
    args = ap.parse_args()

    # Windows のコンソール（cp932）でも文字化けせず、Git Bash でも即時に表示されるようにする
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    load_dotenv()
    if args.test_line:
        return 0 if notify("【ITS】LINE 通知のテストです") else 1

    with open(args.config, "rb") as f:
        config = tomllib.load(f)
    browser_cfg, watch_cfg, search = config["browser"], config["watch"], config["search"]
    facilities = [f["name"] for f in config["facilities"]]
    interval = max(watch_cfg["interval_sec"], MIN_INTERVAL_SEC)
    wait_ms = max(watch_cfg["request_wait_ms"], MIN_REQUEST_WAIT_MS)

    with sync_playwright() as p:
        if browser_cfg.get("cdp_url"):
            try:
                browser = p.chromium.connect_over_cdp(browser_cfg["cdp_url"])
            except Exception:
                print(f"Chrome に接続できません（{browser_cfg['cdp_url']}）。"
                      "README の手順で --remote-debugging-port を付けて Chrome を起動してから実行してください")
                return 1
            context = browser.contexts[0]
        else:
            context = p.chromium.launch_persistent_context(
                browser_cfg["profile_dir"], headless=False, locale="ja-JP"
            )
        page = context.new_page()
        cal = open_calendar(page, watch_cfg)
        if cal is None:
            return 1

        last_message = None
        for i in range(watch_cfg["max_rounds"]):
            if i:
                cal.wait_for_timeout(interval * 1000)
                cal.reload()
                cal.wait_for_load_state("networkidle")
            if is_captcha_page(cal):
                notify("【ITS】セッションが切れました。再実行して Turnstile を通過してください")
                save_capture(cal, "calendar_captcha")
                return 1
            found = search_all(cal, facilities, search, wait_ms)
            if i == 0:
                save_capture(cal, "calendar")
            print(f"{dt.datetime.now():%H:%M:%S} 条件に合う空き {len(found)} 件")
            for v in found:
                print(f"  {v}")
            message = "【ITS】空き状況（○空き △残りわずか）\n" + "\n".join(map(str, found)) if found else None
            # 前回と同じ内容は送らない（LINE の無料枠は月 200 通）
            if message and message != last_message:
                notify(message)
            last_message = message
        page.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
