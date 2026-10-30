"""ITS健保 保養施設の空き照会（半自動）。

Turnstile は人が通過させ、それ以降の照会・保存・通知を自動で行う。
"""
import argparse
import datetime as dt
import pathlib
import sys
import time
import tomllib

from playwright.sync_api import Page, sync_playwright

from .line import load_dotenv, notify
from .sitecodec import empty_apply_url

CAPTURE_DIR = pathlib.Path("captures")
MIN_RELOAD_SEC = 180


def is_captcha_page(page: Page) -> bool:
    return "/apply/capture_check" in page.url or page.locator(".cf-turnstile").count() > 0


def save_capture(page: Page, label: str) -> pathlib.Path:
    CAPTURE_DIR.mkdir(exist_ok=True)
    stem = CAPTURE_DIR / f"{dt.datetime.now():%Y%m%d-%H%M%S}_{label}"
    stem.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(stem.with_suffix(".png")), full_page=True)
    print(f"保存: {stem}.html / .png  ({page.url})")
    return stem


def wait_for_human(page: Page, timeout_sec: int, facility: str) -> bool:
    """Turnstile を人が通過して次の画面に進むまで待つ。"""
    print("\a")
    notify(f"【ITS】{facility}: ブラウザで「確認」にチェックして「次へ」を押してください")
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not is_captcha_page(page):
            return True
        page.wait_for_timeout(1000)
    return False


def watch(page: Page, facility: dict, cfg: dict) -> None:
    name = facility["name"]
    url = empty_apply_url(facility["apply_id"])
    page.goto(url)

    if is_captcha_page(page):
        if not wait_for_human(page, cfg["captcha_timeout_sec"], name):
            notify(f"【ITS】{name}: Turnstile 待ちがタイムアウトしました")
            return
    page.wait_for_load_state("networkidle")
    passed_at = time.monotonic()
    save_capture(page, f"{facility['apply_id']}_00")

    # 同じセッションでどれだけ再照会できるかを計測する
    interval = max(cfg["reload_interval_sec"], MIN_RELOAD_SEC)
    for i in range(1, cfg["max_reloads"] + 1):
        page.wait_for_timeout(interval * 1000)
        page.reload()
        page.wait_for_load_state("networkidle")
        elapsed = int(time.monotonic() - passed_at)
        if is_captcha_page(page):
            notify(f"【ITS】{name}: 通過から {elapsed} 秒後の {i} 回目の再読み込みで Turnstile に戻りました")
            save_capture(page, f"{facility['apply_id']}_{i:02d}_captcha")
            return
        save_capture(page, f"{facility['apply_id']}_{i:02d}")
        print(f"{i} 回目の再読み込み OK（通過から {elapsed} 秒）")
    notify(f"【ITS】{name}: {cfg['max_reloads']} 回の再読み込みでセッションは維持されました")


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m its_watch")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--test-line", action="store_true", help="LINE 通知のテストだけ行う")
    args = ap.parse_args()

    # Windows のコンソール（cp932）でも文字化けしないようにする
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    if args.test_line:
        return 0 if notify("【ITS】LINE 通知のテストです") else 1

    with open(args.config, "rb") as f:
        config = tomllib.load(f)
    browser_cfg, watch_cfg = config["browser"], config["watch"]

    with sync_playwright() as p:
        if browser_cfg.get("cdp_url"):
            browser = p.chromium.connect_over_cdp(browser_cfg["cdp_url"])
            context = browser.contexts[0]
        else:
            context = p.chromium.launch_persistent_context(
                browser_cfg["profile_dir"], headless=False, locale="ja-JP"
            )
        page = context.new_page()
        for facility in config["facilities"]:
            watch(page, facility, watch_cfg)
        page.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
