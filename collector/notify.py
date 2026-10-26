"""텔레그램 알림. 수집이 끝난 뒤 새로 나온 할인, 판매 마감이 내일·오늘인 할인, 수집 실패를 봇으로 보낸다.

- 토큰·받는 사람은 Secrets(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)에서 읽는다. 없으면 아무것도 하지 않는다.
  받는 사람은 쉼표로 여럿 넣을 수 있다.
- 보낸 것은 data/telegram_sent.json에 남겨 같은 소식을 두 번 보내지 않는다 (행사 id와 알림 종류만, 받는 사람 정보 없음).
- 처음 켤 때는 지금 있는 행사를 보낸 것으로 치고 '연결 완료' 한 통만 보낸다 (수십 건이 한꺼번에 오지 않게).
- 알림이 실패해도 수집·배포는 계속한다 (collect.yml에서 continue-on-error).
"""

import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from .status import display_status, today_kst

ROOT = Path(__file__).resolve().parent.parent
DEALS = ROOT / "data" / "deals.json"
STATE = ROOT / "data" / "telegram_sent.json"
SITE = "https://theddack.github.io/icn-air-deals/"
API = "https://api.telegram.org/bot{token}/{method}"
UA = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"

NEW_MAX_AGE_DAYS = 3   # 처음 본 지 이 일수 안인 행사만 '새 할인'으로 (기사가 더해져 id가 바뀐 옛 행사를 다시 보내지 않게)
LIST_MAX = 10          # 한 메시지에 넣는 행사 수
KEEP_DAYS = 60         # 보낸 기록 보관 기간
SECTION = {"flight": "항공권", "domestic": "국내선", "hotel": "숙박"}
WEEK = "월화수목금토일"


def md(iso):
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}({WEEK[d.weekday()]})"


def _places(deal):
    """도착지 이름 (사이트 카드와 같은 기준: '한국'·'인천'으로 들어오는 노선은 빼고, 공항 코드는 지운다)."""
    out = []
    for r in deal.get("routes") or []:
        dest = r.get("destination") or ""
        if not dest or dest == "한국" or dest.startswith("인천"):
            continue
        name = dest.split("(")[0].strip()
        if name not in out:
            out.append(name)
    return out


def line(deal, today):
    """행사 한 줄: [구분] 주인 · 목적지(또는 행사 이름) — 할인 · 판매 기한 · 출처."""
    e = html.escape
    where = " · ".join(_places(deal)[:2]) if deal.get("section") != "hotel" else " · ".join((deal.get("regions") or [])[:2])
    title = where or (deal.get("event_name") or deal.get("headline") or "")[:40]
    bits = [deal.get("discount") or "할인 조건은 공식 페이지에서 확인"]
    if deal.get("sale_end"):
        left = (date.fromisoformat(deal["sale_end"]) - today).days
        bits.append("오늘 마감" if left == 0 else f"판매 ~{md(deal['sale_end'])}" + (f" (D-{left})" if left <= 3 else ""))
    elif deal.get("sale_start") and deal["sale_start"] > today.isoformat():
        bits.append(f"{md(deal['sale_start'])} 판매 시작")
    src = ("판매처" if deal.get("kind") == "platform" or deal.get("section") == "hotel" else "항공사") + " 공식" \
        if deal.get("verification") == "official" else f"뉴스 {len(deal.get('articles') or [])}건"
    link, label = deal.get("official_url"), "공식 홈페이지"
    if not link:
        link, label = (deal.get("articles") or [{}])[0].get("url"), "기사"
    head = f"[{SECTION.get(deal.get('section'), '항공권')}] {e(deal.get('airline') or '')} · <b>{e(title)}</b>"
    tail = " · ".join(e(b) for b in bits) + f" · {e(src)}"
    if link and link.startswith(("http://", "https://")):
        tail += f' · <a href="{e(link, quote=True)}">{label}</a>'
    return f"• {head}\n  {tail}"


def pick(deals, sent, today):
    """→ (새 할인 목록, 곧 마감 목록). 마감·진행 여부 미확인·인천 외 출발은 뺀다."""
    new, closing = [], []
    cutoff = (today - timedelta(days=NEW_MAX_AGE_DAYS)).isoformat()
    for d in deals:
        st = display_status(d, today)
        if st in ("ended", "stale") or d.get("from_icn") == "no":
            continue
        if d["id"] not in sent and (d.get("first_seen") or "")[:10] >= cutoff:
            new.append(d)
        if st == "live" and d.get("sale_end") and (date.fromisoformat(d["sale_end"]) - today).days <= 1 \
                and f"{d['id']}:closing" not in sent:
            closing.append(d)
    # 새 할인에 이미 들어간 행사는 곧 마감에 또 넣지 않는다 (줄에 D-day가 붙는다)
    closing = [d for d in closing if d not in new]
    # 공식 확인 먼저, 그다음 마감 가까운 순
    new.sort(key=lambda d: (d.get("verification") != "official", d.get("sale_end") or "9999"))
    return new, closing


def messages(new, closing, failed, today):
    out = []
    if new:
        body = "\n".join(line(d, today) for d in new[:LIST_MAX])
        more = f"\n외 {len(new) - LIST_MAX}건은 사이트에서 확인하세요." if len(new) > LIST_MAX else ""
        out.append(f"✈ 새 할인 {len(new)}건\n\n{body}{more}")
    if closing:
        body = "\n".join(line(d, today) for d in closing[:LIST_MAX])
        out.append(f"⏰ 곧 마감 {len(closing)}건 (오늘·내일)\n\n{body}")
    if failed:
        out.append(f"⚠ 직전 수집에서 뉴스 검색어 {failed}개가 실패했습니다. 일부 행사가 빠졌을 수 있습니다.")
    return [m + f'\n\n<a href="{SITE}">ICN 특가 레이더 열기</a>' for m in out]


def send(token, chat_id, text, tries=5):
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    for i in range(tries):
        req = urllib.request.Request(API.format(token=token, method="sendMessage"), data=data, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            # 429(요청 과다): GitHub 공용 러너는 같은 IP를 여럿이 써서 난다 (2026-10-26). 알려 준 시간만큼 기다린다
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


def run(deals_data, state, today, sender):
    """→ 새 state. sender(text)로 보낸다. 보낸 뒤에만 기록해서 실패하면 다음 수집 때 다시 보낸다."""
    deals = deals_data.get("deals", [])
    sent = dict(state.get("sent", {}))
    if not state.get("started"):
        # 처음: 지금 있는 행사는 보낸 것으로 친다
        for d in deals:
            sent[d["id"]] = today.isoformat()
        live = sum(display_status(d, today) not in ("ended", "stale") for d in deals)
        sender(f"ICN 특가 레이더 알림이 연결됐습니다.\n지금 볼 수 있는 할인 {live}건 · 앞으로 새 할인과 곧 마감되는 할인을 보내 드려요."
               f'\n\n<a href="{SITE}">ICN 특가 레이더 열기</a>')
        return {"started": today.isoformat(), "sent": sent}
    new, closing = pick(deals, sent, today)
    failed = (deals_data.get("stats") or {}).get("failed_queries") or 0
    fail_key = f"failed:{today.isoformat()}"
    failed = failed if failed and fail_key not in sent else 0
    for text in messages(new, closing, failed, today):
        sender(text)
    for d in new:
        sent[d["id"]] = today.isoformat()
        if d.get("sale_end") and (date.fromisoformat(d["sale_end"]) - today).days <= 1:
            sent[f"{d['id']}:closing"] = today.isoformat()
    for d in closing:
        sent[f"{d['id']}:closing"] = today.isoformat()
    if failed:
        sent[fail_key] = today.isoformat()
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    return {**state, "sent": {k: v for k, v in sent.items() if v >= cutoff}}


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not token or not chats:
        print("텔레그램 비밀값이 없어 알림을 건너뜁니다.")
        return 0
    deals_data = json.loads(DEALS.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    count = [0]

    def sender(text):
        for c in chats:
            send(token, c, text)
        count[0] += 1

    new_state = run(deals_data, state, today_kst(), sender)
    STATE.write_text(json.dumps(new_state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[notify] 메시지 {count[0]}통을 {len(chats)}곳에 보냈습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
