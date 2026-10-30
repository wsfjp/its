"""「空き状況カレンダー」画面から、全施設の空きを読み取る。

カレンダー画面は施設ごとのタブを持ち、月ごとの表をページ内の getMonthDays()
で読み込む。Turnstile を通過したブラウザの中で、画面と同じ操作をして読み取る。

カレンダーのセル:
  td[data-join-time]  class が empty=空き / a_little=残りわずか / full=満室 / over=受付外
受付前の月を要求すると、受付中の最終月の表が返る（その月は「翌月」ボタンが disabled）。
"""
import datetime as dt
from dataclasses import dataclass

from playwright.sync_api import Page

WEEKDAYS = "月火水木金土日"
STATUS_LABEL = {"empty": "○", "a_little": "△"}


@dataclass
class Vacancy:
    facility: str
    day: dt.date
    status: str  # empty / a_little

    def __str__(self) -> str:
        return f"{self.day:%m/%d}({WEEKDAYS[self.day.weekday()]}){STATUS_LABEL[self.status]} {self.facility}"


def facility_ids(cal: Page) -> dict[str, str]:
    """タブの施設名 → apply_service_id。"""
    return cal.locator("#top_tabs a").evaluate_all(
        """links => Object.fromEntries(links.map(a => [
            a.textContent.trim().replace(/\\s+/g, ' '),
            a.getAttribute('onclick').match(/as_(\\d+)/)[1],
        ]))"""
    )


def load_month(
    cal: Page, service_id: str, month: dt.date, nights: int, wait_ms: int
) -> tuple[list[tuple[dt.date, str]], bool]:
    """1 か月分の (日付, 状態) と、翌月が受付中かどうかを返す。"""
    cal.evaluate(
        "([id, d, n]) => getMonthDays(id, d, n)",
        [service_id, month.strftime("%Y-%m-01"), nights],
    )
    cal.wait_for_timeout(wait_ms)
    cal.locator("#loadingView").wait_for(state="hidden")
    body = cal.locator(f"#tcb{service_id}_{nights}")
    has_next = body.locator("#nextMonth:not([disabled])").count() > 0
    cells = body.locator("td[data-join-time]").evaluate_all(
        "tds => tds.map(td => [td.getAttribute('data-join-time'), td.className])"
    )
    result = []
    for join_time, classes in cells:
        status = next((c for c in classes.split() if c in STATUS_LABEL), None)
        day = dt.date.fromisoformat(join_time[:10])
        # 受付前の月を要求したときに返る別の月の表は無視する
        if status and (day.year, day.month) == (month.year, month.month):
            result.append((day, status))
    return result, has_next


def months_between(start: dt.date, end: dt.date) -> list[dt.date]:
    months, m = [], start.replace(day=1)
    while m <= end:
        months.append(m)
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return months


def search_period(search: dict) -> tuple[dt.date, dt.date]:
    """対象期間。既定は今日から months_ahead か月先の月末まで。

    カレンダーは当月・翌月・翌々月の 3 か月分が公開され、翌々月は空室公開日
    （通常 27 日）までは空室なしで表示される。
    """
    today = dt.date.today()
    start = dt.date.fromisoformat(search["date_from"]) if search.get("date_from") else today
    if search.get("date_to"):
        end = dt.date.fromisoformat(search["date_to"])
    else:
        months = today.month - 1 + search.get("months_ahead", 2) + 1
        end = dt.date(today.year + months // 12, months % 12 + 1, 1) - dt.timedelta(days=1)
    return max(start, today), end


def search_all(cal: Page, facilities: list[str], search: dict, wait_ms: int) -> list[Vacancy]:
    """条件に合う空きを、施設の優先順 → 曜日の優先順 → 日付の順で返す。"""
    ids = facility_ids(cal)
    start, end = search_period(search)
    weekdays = search.get("weekdays") or list(WEEKDAYS)
    found = []
    for name in facilities:
        if name not in ids:
            print(f"施設名がカレンダーにありません: {name}（候補: {', '.join(ids)}）")
            continue
        for month in months_between(start, end):
            days, has_next = load_month(cal, ids[name], month, search["nights"], wait_ms)
            for day, status in days:
                if start <= day <= end and WEEKDAYS[day.weekday()] in weekdays:
                    found.append(Vacancy(name, day, status))
            if not has_next:
                break
    found.sort(key=lambda v: (facilities.index(v.facility), weekdays.index(WEEKDAYS[v.day.weekday()]), v.day))
    return found
