"""条件に合う枠の仮予約（メールアドレス送信まで）。

画面の流れ:
  申込画面 (/apply/empty_new)
    → 希望日・泊数・人数・部屋数を入れて「空き検索」→ 部屋一覧 (#coma_search_result)
    → 部屋にチェックして「予約手続きに進む」（ここから 30 分間部屋が確保される）
    → 個人情報の取り扱い (/apply/rule)「同意する」
    → メールアドレス入力 (/apply/email_input)「送信」→ 確認ダイアログ
    → 送信完了 (/apply/send_complete)。以降はメール記載の URL から手作業

モード（config.toml の [reserve] mode）:
  off     仮予約しない（空きの通知のみ）
  dry_run 部屋の選択までして「予約手続きに進む」の手前で止める（部屋は確保されない）
  submit  メールアドレス送信まで行う（30 分で失効する仮予約になる）
"""
import os
import re

from playwright.sync_api import Page

from .calendar import Vacancy


def pick_room(page: Page, persons: int) -> dict | None:
    """部屋一覧から、人数が収まる空き部屋のうち定員の最も小さいものを選ぶ。"""
    rows = page.locator("#coma_search_result tr").evaluate_all(
        """trs => trs.map(tr => {
            const td = [...tr.querySelectorAll('td')].map(t => t.textContent.trim());
            const box = tr.querySelector('input[type=checkbox]');
            return {value: box && box.value, room: td[1], date: td[2], type: td[3], persons: td[4], status: td[5]};
        })"""
    )
    candidates = []
    for row in rows:
        m = re.match(r"(\d+)\s*～\s*(\d+)", row["persons"] or "")
        if row["value"] and row["status"] == "空き" and m and int(m[1]) <= persons <= int(m[2]):
            candidates.append((int(m[2]), row))
    return min(candidates, key=lambda c: c[0])[1] if candidates else None


def search_rooms(page: Page, vacancy: Vacancy, nights: int, persons: int) -> dict | None:
    """申込画面で条件を入れて「空き検索」し、選んだ部屋にチェックを入れる。"""
    day = vacancy.day.isoformat()
    if page.locator(f"#apply_join_time option[value='{day}']").count() == 0:
        print(f"申込画面の希望日に {day} がありません（埋まった可能性）")
        return None
    page.select_option("#apply_join_time", day)
    page.select_option("#apply_night_count", str(nights))
    page.fill("#apply_stay_persons", str(persons))
    page.select_option("#house_select", "1")
    page.click("input[value='空き検索']")
    page.locator("#coma_search_result, #errorExplanation").first.wait_for(timeout=20000)
    room = pick_room(page, persons)
    if room is None:
        print(f"{day}: {persons} 名で泊まれる空き部屋がありません")
        return None
    page.check(f"#coma_search_result input[value='{room['value']}']")
    print(f"選んだ部屋: {room['room']} {room['type']}（{room['persons']} 名）{room['date']}")
    return room


def submit(page: Page) -> bool:
    """「予約手続きに進む」から、同意・メールアドレス送信まで行う。"""
    email = os.environ.get("ITS_EMAIL")
    if not email:
        print(".env に ITS_EMAIL を設定してください")
        return False
    # 各画面は表示後に history.pushState で URL を書き換えるため、URL ではなく要素で待つ
    page.click("input[value='予約手続きに進む']")
    page.click("input[value='同意する']", timeout=20000)
    page.fill("#email_inp", email, timeout=20000)
    # 「メールを送信します。よろしいですか？」の確認に OK する
    page.once("dialog", lambda d: d.accept())
    page.click("input[value='送信']")
    page.get_by_text("メール送信を完了しました").wait_for(timeout=20000)
    return True
