"""as.its-kenpo.or.jp の `s` パラメータの変換。

s = base64( reverse( base64(クエリ文字列) ) )
"""
import base64
from urllib.parse import quote

BASE_URL = "https://as.its-kenpo.or.jp"


def encode_s(query: str) -> str:
    inner = base64.b64encode(query.encode()).decode()
    return base64.b64encode(inner[::-1].encode()).decode()


def decode_s(s: str) -> str:
    inner = base64.b64decode(s).decode()[::-1]
    return base64.b64decode(inner + "=" * (-len(inner) % 4)).decode()


def empty_apply_url(apply_id: int) -> str:
    """施設の空き照会（申込）入口の URL。"""
    return f"{BASE_URL}/apply/empty_new?s={quote(encode_s(f'empty=true&id={apply_id}'))}"
