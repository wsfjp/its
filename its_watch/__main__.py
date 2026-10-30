"""ITS健保 保養施設の空き照会（半自動）。

Turnstile は人が通過させ、それ以降の照会・通知を自動で行う。
"""
import argparse
import json
import datetime as dt
import pathlib
import re
import sys
import time
import tomllib
import urllib.request

from playwright.sync_api import Page, sync_playwright

from .calendar import Vacancy, facility_ids, open_apply_page, search_all
from .line import load_dotenv, notify
from .reserve import search_rooms, submit
from .sitecodec import empty_apply_url

CAPTURE_DIR = pathlib.Path("captures")
DEFAULT_PUBLIC_URL = "https://www.its-kenpo.or.jp/shisetsu/keiyaku/tsunen/katsuura/aki.html"
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


class Chrome:
    """ブラウザへの接続。CDP 接続なら、Turnstile の間だけ切断できる。"""

    def __init__(self, p, browser_cfg: dict):
        self.p, self.cdp_url = p, browser_cfg.get("cdp_url")
        if self.cdp_url:
            self.connect()
        else:
            self.browser = None
            self.context = p.chromium.launch_persistent_context(
                browser_cfg["profile_dir"], headless=False, locale="ja-JP"
            )

    def connect(self) -> None:
        self.browser = self.p.chromium.connect_over_cdp(self.cdp_url)
        self.context = self.browser.contexts[0]

    def find_page(self, part: str) -> Page | None:
        pages = [pg for pg in self.context.pages if part in pg.url]
        return pages[-1] if pages else None

    def tab_states(self) -> list[tuple[str, str]]:
        """ページに接続せずに、開いているタブの (URL, タイトル) を取得する。"""
        with urllib.request.urlopen(f"{self.cdp_url}/json/list", timeout=5) as r:
            return [(t["url"], t["title"]) for t in json.load(r) if t.get("type") == "page"]

    def passed_page(self, done: str) -> Page | None:
        page = self.find_page(done)
        if page is None:
            return None
        try:
            page.wait_for_load_state("domcontentloaded")
            return None if is_captcha_page(page) else page
        except Exception:
            return None  # 画面遷移の途中

    def pass_turnstile(self, timeout_sec: int, done: str) -> Page | None:
        """Turnstile を人に通過してもらい、通過後の画面（URL に done を含むタブ）を返す。

        接続したままだと Turnstile の判定に失敗するため、CDP 接続なら切断し、タブの URL と
        タイトルだけを見て待つ。変化したら接続して画面を確かめ、まだ Turnstile なら待ち直す。
        """
        # 判定だけで自動的に通過している場合
        page = self.passed_page(done)
        if page is not None:
            return page
        print("\a")
        notify("【ITS】ブラウザで「確認」にチェックして「次へ」を押してください")
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.cdp_url:
                before = self.tab_states()
                self.browser.close()  # CDP 接続を切るだけで、Chrome とタブはそのまま残る
                try:
                    while time.monotonic() < deadline and self.tab_states() == before:
                        time.sleep(2)
                finally:
                    self.connect()
            else:
                time.sleep(2)
            page = self.passed_page(done)
            if page is not None:
                return page
        return None


def open_calendar(chrome: Chrome, cfg: dict) -> Page | None:
    """「空き状況カレンダー」（全施設のタブがある画面）を開く。

    entry = "public": ITS ホームページの施設紹介「空き状況確認」タブ（Turnstile なし）から開く。
    entry = "apply" : 申込画面に入り（Turnstile は人が通過）、「空き状況カレンダー」リンクから開く。
    """
    page = chrome.context.new_page()
    if cfg.get("entry", "public") == "public":
        return open_calendar_public(chrome, page, cfg.get("public_url", DEFAULT_PUBLIC_URL), cfg["captcha_timeout_sec"])
    page.goto(empty_apply_url(cfg["entry_apply_id"]))
    if is_captcha_page(page):
        page = chrome.pass_turnstile(cfg["captcha_timeout_sec"], "/apply/empty_new")
        if page is None:
            notify("【ITS】Turnstile 待ちがタイムアウトしました")
            return None
    page.wait_for_load_state("networkidle")
    with page.context.expect_page() as popup:
        page.click("#showStatus")
    cal = popup.value
    cal.wait_for_load_state("networkidle")
    return cal


def open_calendar_public(chrome: Chrome, page: Page, url: str, timeout_sec: int) -> Page | None:
    """施設紹介ページに埋め込まれた予約システムの画面で「空き状況確認」を押す。"""
    page.goto(url)
    frame = page.frame_locator("#iframe_reserve")
    button = frame.locator("input[value='空き状況確認'], button:has-text('空き状況確認')").first
    button.wait_for(timeout=20000)
    try:
        with page.context.expect_page(timeout=15000) as popup:
            button.click()
        cal = popup.value
    except Exception:
        # 別窓ではなく埋め込み画面の中で開いた場合
        frames = [f for f in page.frames if "empty_calendar" in f.url]
        if not frames:
            print("カレンダーが開きませんでした。config.toml の entry を \"apply\" にすると従来の入口を使います")
            save_capture(page, "public_entry_failed")
            return None
        cal = page.context.new_page()
        cal.goto(frames[0].url)
    cal.wait_for_load_state("domcontentloaded")
    if is_captcha_page(cal):
        cal = chrome.pass_turnstile(timeout_sec, "/apply/calendar")
        if cal is None:
            notify("【ITS】Turnstile 待ちがタイムアウトしました")
            return None
    try:
        cal.locator("#top_tabs").wait_for(timeout=20000)
    except Exception:
        print(f"カレンダー画面ではありません: {cal.url}")
        save_capture(cal, "public_entry_failed")
        return None
    return cal


def reserve(chrome: Chrome, ids: dict[str, str], found: list[Vacancy], config: dict) -> bool:
    """優先順に仮予約を試みる。仮予約した（dry_run なら部屋を選べた）ら True。"""
    mode = config["reserve"]["mode"]
    search, watch_cfg = config["search"], config["watch"]
    wait_ms = max(watch_cfg["request_wait_ms"], MIN_REQUEST_WAIT_MS)
    # 前の回の申込画面が残っていると、Turnstile 通過の判定を誤るので閉じておく
    for pg in chrome.context.pages:
        if "/apply/empty_new" in pg.url or "/apply/capture_check" in pg.url:
            pg.close()
    for v in found[: config["reserve"]["max_attempts"]]:
        print(f"仮予約を試みます（{mode}）: {v}")
        # 日付をクリックするとカレンダーの窓は閉じるので、無ければ開き直す
        cal = chrome.find_page("/apply/calendar") or open_calendar(chrome, watch_cfg)
        if cal is None:
            return False
        page = open_apply_page(cal, ids[v.facility], v.day, search["nights"], wait_ms)
        if is_captcha_page(page):
            page = chrome.pass_turnstile(watch_cfg["captcha_timeout_sec"], "/apply/empty_new")
            if page is None:
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
    ap.add_argument("--save", action="store_true", help="カレンダー画面を captures/ に保存する")
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
        try:
            chrome = Chrome(p, browser_cfg)
        except Exception:
            print(f"Chrome に接続できません（{browser_cfg['cdp_url']}）。"
                  "README の手順で --remote-debugging-port を付けて Chrome を起動してから実行してください")
            return 1
        last_message = None
        for i in range(watch_cfg["max_rounds"]):
            if i:
                time.sleep(interval)
                print(f"{dt.datetime.now():%H:%M:%S} 確認 {i + 1}/{watch_cfg['max_rounds']} 回目")
                # 前の回に開いたカレンダー関係のタブを閉じる（申込画面は残す）
                for pg in chrome.context.pages:
                    if any(k in pg.url for k in ("/apply/calendar", "/apply/empty_calendar", "its-kenpo.or.jp/shisetsu/")):
                        pg.close()
            # カレンダーはフォーム送信の結果画面なので、再読み込みせず毎回開き直す
            cal = open_calendar(chrome, watch_cfg)
            if cal is None:
                return 1
            found = search_all(cal, facilities, search, wait_ms)
            if i == 0 and args.save:
                save_capture(cal, "calendar")
            print(f"{dt.datetime.now():%H:%M:%S} 条件に合う空き {len(found)} 件（{', '.join(facilities)}）")
            for v in found:
                print(f"  {v}")
            message = "【ITS】空き状況（○空き △残りわずか）\n" + "\n".join(map(str, found)) if found else None
            # 前回と同じ内容は送らない（LINE の無料枠は月 200 通）
            if message and message != last_message:
                notify(message)
            last_message = message
            if found and config["reserve"]["mode"] != "off":
                if reserve(chrome, facility_ids(cal), found, config):
                    break
            if i + 1 < watch_cfg["max_rounds"]:
                next_at = dt.datetime.now() + dt.timedelta(seconds=interval)
                print(f"次の確認は {next_at:%H:%M:%S} です（Ctrl+C で終了）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n中断しました")
        sys.exit(130)
