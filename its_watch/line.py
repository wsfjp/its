"""LINE Messaging API での通知。"""
import json
import os
import re
import urllib.error
import urllib.request

PUSH_URL = "https://api.line.me/v2/bot/message/push"


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    # Windows のメモ帳で保存すると BOM が付くため utf-8-sig で読む
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def notify(text: str) -> bool:
    """LINE に送信する。未設定なら標準出力のみで False を返す。"""
    print(f"[notify] {text}")
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    to = os.environ.get("LINE_TO_USER_ID")
    if not token or not to:
        return False
    if not re.fullmatch(r"U[0-9a-f]{32}", to):
        print(f"[notify] LINE_TO_USER_ID の形式が違います（{len(to)} 文字）。"
              "LINE Developers の「チャネル基本設定」→「あなたのユーザーID」"
              "（U で始まる 33 文字）を設定してください")
        return False
    body = json.dumps({"to": to, "messages": [{"type": "text", "text": text[:5000]}]})
    req = urllib.request.Request(
        PUSH_URL,
        data=body.encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except urllib.error.HTTPError as e:  # 通知失敗で監視自体は止めない
        print(f"[notify] LINE 送信失敗: {e} {e.read().decode(errors='replace')}")
    except Exception as e:
        print(f"[notify] LINE 送信失敗: {e}")
        return False
