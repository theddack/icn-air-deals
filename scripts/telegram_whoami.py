"""텔레그램 봇 연결 확인용. 봇에게 메시지를 보낸 개인 대화마다 그 대화의 chat id를 봇이 직접 답장으로 알려 준다.

토큰은 Secrets(TELEGRAM_BOT_TOKEN)에서 읽는다. 저장소가 공개라 Actions 로그에는 chat id·이름을 남기지 않고
몇 곳에 보냈는지만 찍는다. 봇은 최근 24시간 안에 받은 메시지만 볼 수 있다 (getUpdates).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"


def call(token, method, params=None, tries=5):
    """시간 초과·429(요청 과다)는 기다렸다 다시 한다. GitHub 공용 러너는 같은 IP를 여럿이 써서 429가 난다 (2026-10-26)."""
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    for i in range(tries):
        req = urllib.request.Request(API.format(token=token, method=method), data=data,
                                     headers={"User-Agent": "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            try:
                wait = int(json.load(e).get("parameters", {}).get("retry_after", 5))
            except Exception:
                wait = 5
        except (TimeoutError, urllib.error.URLError):
            if i == tries - 1:
                raise
            wait = 5
        time.sleep(min(wait, 60) + 1)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN이 Secrets에 없습니다. 저장소 Settings → Secrets and variables → Actions에 등록하세요.")
        return 1
    try:
        me = call(token, "getMe")
        updates = call(token, "getUpdates")
    except Exception as e:
        code = getattr(e, "code", "")
        hint = "토큰을 다시 확인하세요." if code in (401, 404) else "텔레그램 쪽 일시 문제일 수 있으니 잠시 뒤 다시 실행하세요."
        print(f"텔레그램 API 호출 실패: {type(e).__name__} {code} — {hint}")
        return 1
    print(f"봇 확인: @{me['result']['username']}")
    chats = {}
    for u in updates.get("result", []):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            chats[chat["id"]] = True
    if not chats:
        print("최근 24시간 안에 봇에게 온 메시지가 없습니다. 텔레그램에서 봇에게 아무 글이나 보낸 뒤 다시 실행하세요.")
        return 1
    for chat_id in chats:
        call(token, "sendMessage", {"chat_id": chat_id, "text":
             f"ICN 특가 레이더 연결 확인\n이 대화의 chat id: {chat_id}\n\nGitHub 저장소 Secrets의 TELEGRAM_CHAT_ID에 이 숫자를 넣으세요."})
    print(f"개인 대화 {len(chats)}곳에 chat id를 답장으로 보냈습니다 (로그에는 남기지 않음).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
