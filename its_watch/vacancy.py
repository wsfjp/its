"""申込画面の「希望日」プルダウンから空き日を読み取り、条件で絞り込む。

プルダウンには空きのある日だけが並ぶ（画面の注記「※空きが無い日付は表示されません」）。
"""
import datetime as dt
import json
import pathlib

from playwright.sync_api import Page

WEEKDAYS = "月火水木金土日"
STATE_FILE = pathlib.Path("state.json")


def available_dates(page: Page) -> list[dt.date]:
    values = page.locator("#apply_join_time option").evaluate_all(
        "opts => opts.map(o => o.value).filter(v => v)"
    )
    return [dt.date.fromisoformat(v) for v in values]


def matches(day: dt.date, facility: dict) -> bool:
    weekdays = facility.get("weekdays") or []
    if weekdays and WEEKDAYS[day.weekday()] not in weekdays:
        return False
    if facility.get("date_from") and day < dt.date.fromisoformat(facility["date_from"]):
        return False
    if facility.get("date_to") and day > dt.date.fromisoformat(facility["date_to"]):
        return False
    return True


def fmt(day: dt.date) -> str:
    return f"{day:%m/%d}({WEEKDAYS[day.weekday()]})"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def new_matches(page: Page, facility: dict) -> tuple[list[dt.date], list[dt.date]]:
    """条件に合う空き日と、そのうち前回の確認以降に新しく現れた日を返す。

    一度消えて再び空いた日も「新しい」として扱う。
    """
    found = [d for d in available_dates(page) if matches(d, facility)]
    state = load_state()
    key = str(facility["apply_id"])
    previous = set(state.get(key, []))
    fresh = [d for d in found if d.isoformat() not in previous]
    state[key] = [d.isoformat() for d in found]
    save_state(state)
    return found, fresh
