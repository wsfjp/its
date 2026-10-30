"""ITS健保 保養施設の空き照会（半自動）。

Turnstile は人が通過させ、それ以降の照会・通知を自動で行う。
"""
import argparse
import datetime as dt
import pathlib
import re
import sys
import time
import tomllib

from playwright.sync_api import Page, sync_playwright

from .calendar import Vacancy, facility_ids, search_all
from .line import load_dotenv, notify
from .reserve import search_rooms, submit
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


def reserve(page: Page, cal: Page, found: list[Vacancy], config: dict) -> bool:
    """優先順に仮予約を試みる。仮予約した（dry_run なら部屋を選べた）ら True。"""
    mode = config["reserve"]["mode"]
    search, watch_cfg = config["search"], config["watch"]
    ids = facility_ids(cal)
    for v in found[: config["reserve"]["max_attempts"]]:
        print(f"仮予約を試みます（{mode}）: {v}")
        page.goto(empty_apply_url(int(ids[v.facility])))
        if is_captcha_page(page) and not wait_for_human(page, watch_cfg["captcha_timeout_sec"]):
            notify("【ITS】Turnstile 待ちがタイムアウトしました")
            return False
        page.wait_for_load_state("networkidle")
        room = search_rooms(page, v, search["nights"], search["persons"])
        if room is None:
            continue
        desc = f"{v} 部屋{room['room']} {room['type']}（{room['persons']}名）"
        if mode == "dry_run":
            notify(f"【ITS】[dry_run] 部屋を選びました（仮予約はしていません）\n{desc}")
            return True
        if config["reserve"].get("confirm", True):
            print("\a")
            if input(f"{desc}\nこの部屋で仮予約しますか？ [y/N] ").strip().lower() != "y":
                print("仮予約を中止しました")
                return False
        if submit(page):
            notify(f"【ITS】仮予約しました。30 分以内にメールの URL から手続きしてください\n{desc}")
            return True
        notify(f"【ITS】仮予約に失敗しました\n{desc}")
        save_capture(page, "reserve_failed")
        return False
    return False


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

    try:
        with open(args.config, "rb") as f:
            config = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        m = re.search(r"line (\d+)", str(e))
        lines = pathlib.Path(args.config).read_text(encoding="utf-8").splitlines()
        if m and int(m[1]) <= len(lines):
            print(f"{args.config} の {m[1]} 行目の書き方が正しくありません: {lines[int(m[1]) - 1]}")
        print("コメントは # で始める、= や \" は半角にする、1 行に設定は 1 つ、を確認してください")
        print(f"（詳細: {e}）")
        return 1
    if "reserve" not in config:
        print(f"{args.config} に [reserve] がありません。config.example.toml からコピーしてください")
        return 1
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
            if found and config["reserve"]["mode"] != "off":
                if reserve(page, cal, found, config):
                    break
        page.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
