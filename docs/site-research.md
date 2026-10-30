# ITS健保 施設予約システム 調査メモ（2026-10-30）

対象: https://as.its-kenpo.or.jp/ （Rails 製）

## URL 構造

| 画面 | URL | `s` の中身 |
|---|---|---|
| 保養施設(空き照会) 施設から探す | `/service_group/index?s=...` | `empty=true&id=1` |
| 保養施設(空き照会) カレンダーから探す | `/calendar_apply?s=...` | `empty=true&service_category_id=1` |
| 保養施設(抽選申込) | `/service_group/index?s=...` | `empty=false&id=1` |
| 施設ページ（例: トスラブ箱根ビオーレ） | `/apply_service/index?s=...` | `empty=true&id=4` |
| 施設の申込（空き照会）入口 | `/apply/empty_new?s=...` | `empty=true&id=758` |

`s` パラメータは `base64( reverse( base64(クエリ文字列) ) )`。

```python
import base64
def decode_s(s):
    a = base64.b64decode(s).decode()[::-1]
    return base64.b64decode(a + "=" * (-len(a) % 4)).decode()
```

### 施設 ID（空き照会、一部）

トスラブ箱根ビオーレ=4, トスラブ箱根和奏林=3, トスラブ館山ルアーナ=47,
草津温泉 ホテルヴィレッジ=5, ホテルハーヴェスト那須=6, ホテルハーヴェスト旧軽井沢=39,
ホテルハーヴェスト伊東=9, ラビスタ富士河口湖=256, ホテルオークラ東京ベイ=405 など

## 自動化を妨げる要素

1. **Cloudflare Turnstile**: `/apply/empty_new` は `/apply/capture_check` にリダイレクトされ、
   Turnstile のチャレンジを通らないと空き照会に進めない。`/calendar_apply` にも Turnstile がある。
2. **アクセス遮断**: お知らせ「集中アクセス増加に伴う一定時間の遮断対応について」
   （/notice/144/detail）で、不正と思われるアクセスを一定時間遮断すると明記されている。
3. 調査時点ではトップに「保養施設の抽選処理を実施中のため空き照会停止」の告知が表示されていた。
