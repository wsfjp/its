"""LINE Messaging API での通知。"""
import json
import os
import urllib.request

PUSH_URL = "https://api.line.me/v2/bot/message/push"


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def notify(text: str) -> bool:
    """LINE に送信する。未設定なら標準出力のみで False を返す。"""
    print(f"[notify] {text}")
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    to = os.environ.get("LINE_TO_USER_ID")
    if not token or not to:
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
    except Exception as e:  # 通知失敗で監視自体は止めない
        print(f"[notify] LINE 送信失敗: {e}")
        return False
