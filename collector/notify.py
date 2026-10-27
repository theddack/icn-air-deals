"""텔레그램 알림. 하루 세 시간대(오전·오후·저녁)에 여행 할인 브리핑을 보낸다 (2026-10-27 알림 기획서).

알림 종류 (행사마다 종류별로 한 번만)
- start_today     오늘 판매 시작 (sale_start가 오늘)
- upcoming_d3     곧 시작 (판매 시작 2~3일 전. 하루 늦게 실행돼도 놓치지 않게 2일 전까지)
- upcoming_d1     내일 판매 시작
- closing_today   오늘 판매 마감
- closing_tomorrow 내일 판매 마감
- new             새로 발견 (처음 본 지 3일 안)

시간대 (KST). 시간대마다 메시지는 한 번만, 보낼 것이 없으면 보내지 않는다
- 오전 09~13시: 오늘 시작 · 곧 시작(D-3) · 오늘 마감 · 신규
- 오후 13~18시: 신규 · 오늘 시작 · 오늘 마감
- 저녁 18~21시: 오늘·내일 마감 · 내일 시작 · 오늘 시작 · 신규
- 21시~다음 날 9시에는 보내지 않는다 (밤늦은 알림 부담, 2026-10-27 의견). 22시대 수집은 데이터만 갱신하고,
  그 사이 발견한 행사는 다음 날 오전 '신규'로 간다(처음 본 지 3일 안, 마감된 행사는 제외).
  전날 저녁에 못 보낸 '내일 마감'·'내일 시작'은 다음 날 아침 '오늘 마감'·'오늘 시작'이 된다.
- 앞 시간대가 실행되지 않았으면(예약 지연·누락) 그 시간대 종류도 함께 보낸다.

실행: 예약(09:07 · 14:07 · 18:37 · 20:07) + 수집 작업이 끝날 때마다 (.github/workflows/telegram.yml).
보낸 기록은 data/telegram_sent.json (행사 id·확인된 정보·종류별 발송일, 받는 사람 정보 없음).
수집 실패 경고는 여행 알림에 넣지 않고 Actions 로그와 관리자 대화(TELEGRAM_ADMIN_CHAT_ID, 선택)로만 보낸다.

python -m collector.notify --dry-run [--now 2026-10-27T09:10] : 보내지 않고 메시지와 바뀔 기록만 출력
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from .status import KST, display_status

ROOT = Path(__file__).resolve().parent.parent
DEALS = ROOT / "data" / "deals.json"
STATE = ROOT / "data" / "telegram_sent.json"
SITE = "https://theddack.github.io/icn-air-deals/"
API = "https://api.telegram.org/bot{token}/{method}"
UA = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"

NEW_MAX_AGE_DAYS = 3     # 처음 본 지 이 일수 안인 행사만 '신규'
DATA_STALE_HOURS = 14    # 행사 데이터가 이보다 오래되면 신규로 안내하지 않는다 (수집이 멈춘 것)
KEEP_DAYS = 60           # 보낸 기록 보관 기간
TEXT_MAX = 3800          # 텔레그램 한 메시지 4096자 제한보다 여유 있게
WEEK = "월화수목금토일"
SECTION = {"flight": "항공권", "domestic": "국내선", "hotel": "숙박"}

SLOTS = [  # (이름, 시작 시, 끝 시)
    ("morning", 9, 13),
    ("afternoon", 13, 18),
    ("evening", 18, 21),
]
SLOT_KINDS = {
    "morning": ["start_today", "upcoming_d3", "closing_today", "new"],
    "afternoon": ["new", "start_today", "closing_today"],
    "evening": ["closing_today", "closing_tomorrow", "upcoming_d1", "start_today", "new"],
}
# 한 메시지 안의 순서와 제목. 한 행사가 여러 종류에 해당하면 앞의 것 하나로만 보여 준다
KIND_ORDER = ["start_today", "closing_today", "closing_tomorrow", "upcoming_d1", "upcoming_d3", "new"]
KIND_TITLE = {
    "start_today": "🚀 <b>오늘 판매 시작</b>",
    "closing_today": "⏰ <b>오늘 판매 마감</b>",
    "closing_tomorrow": "⌛ <b>내일 판매 마감</b>",
    "upcoming_d1": "📅 <b>내일 판매 시작</b>",
    "upcoming_d3": "📅 <b>곧 시작하는 행사</b>",
    "new": "🆕 <b>새로 발견한 할인</b>",
}
KIND_SUMMARY = {
    "start_today": "🚀 오늘 판매 시작", "closing_today": "⏰ 오늘 판매 마감", "closing_tomorrow": "⌛ 내일 판매 마감",
    "upcoming_d1": "📅 내일 판매 시작", "upcoming_d3": "📅 곧 시작하는 행사", "new": "🆕 새로 발견한 할인",
}
HEADER = {
    "morning": "☀️ <b>오늘의 여행 할인 브리핑</b>",
    "afternoon": "🆕 <b>새로운 할인 소식</b>",
    "evening": "🌙 <b>오늘의 마감 임박 특가</b>",
}
RULE = "━━━━━━━━━━━━"
NOTE = "※ 표시된 할인·가격은 실제 예약 조건과 다를 수 있습니다."


# ---------------------------------------------------------------- 날짜·시간대

def slot_of(now):
    for name, start, end in SLOTS:
        if start <= now.hour < end:
            return name
    return None


def md(iso):
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def kr_date(d):
    return f"{d.month}월 {d.day}일 {WEEK[d.weekday()]}요일"


def _d(s):
    return date.fromisoformat(s) if s else None


def _dt(s):
    """ISO 문자열 → KST datetime. 날짜만 있으면 그날 0시 ('started'의 예전 형식)."""
    if not s:
        return None
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=KST)


# ---------------------------------------------------------------- 같은 행사 판정 (행사 id가 바뀌어도)

def _norm(s):
    return re.sub(r"[\s\W_]+", "", s or "").lower()


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


def info_of(deal):
    """행사를 다시 알아보는 데 쓰는 확인된 정보. 기사 주소는 해시 앞 10자만."""
    return {
        "airline": deal.get("airline_id"),
        "name": _norm(deal.get("event_name") or ""),
        "sale_start": deal.get("sale_start"),
        "sale_end": deal.get("sale_end"),
        "dests": sorted(_places(deal)),
        "last": deal.get("last_published"),
        "urls": sorted({hashlib.sha1(a["url"].encode()).hexdigest()[:10] for a in deal.get("articles") or [] if a.get("url")})[:30],
    }


UNDATED_SAME_DAYS = 14  # 날짜 없는 행사끼리 이름·도착지로 같다고 볼 최근 기사 날짜 차이 한도


def same_event(a, b):
    """id가 다른 두 행사가 같은 행사인가. 기사가 더해져 묶음의 첫 기사가 바뀌면 id도 바뀐다.
    행사명만으로는 같다고 보지 않는다. 판정 순서 (2026-10-27 보완):
    1. 주인이 다르면 다르다.
    2. 같은 기사를 함께 담고 있으면 같다 (기사 하나는 한 행사에만 묶인다. 날짜 유무와 상관없음).
    3. 양쪽에 모두 있는 판매 시작일 또는 종료일이 서로 다르면 다르다 (판매 기간이 다른 반복 행사).
    4. 날짜가 한쪽에만 있으면(기사가 더해져 정보가 늘어난 경우) 같은 기사로만 잇는다 → 여기서는 다르다.
    5. 날짜가 양쪽 다 같으면 행사명·도착지가 같을 때 같다.
    6. 날짜가 양쪽 다 없으면 행사명·도착지가 같고 최근 기사 날짜가 14일 안일 때만 같다
       (없음끼리를 같은 값으로 치면 한 달 뒤 같은 이름의 다른 회차가 합쳐진다)."""
    if not a or not b or a["airline"] != b["airline"]:
        return False
    if set(a["urls"]) & set(b["urls"]):
        return True
    for k in ("sale_start", "sale_end"):
        if a[k] and b[k] and a[k] != b[k]:
            return False
    if (a["sale_start"], a["sale_end"]) != (b["sale_start"], b["sale_end"]):
        return False
    if not (a["name"] and a["name"] == b["name"] and a["dests"] == b["dests"]):
        return False
    if a["sale_start"] or a["sale_end"]:
        return True
    la, lb = _d(a.get("last")), _d(b.get("last"))
    return bool(la and lb and abs((la - lb).days) <= UNDATED_SAME_DAYS)


def record_for(deal, events):
    """deal의 발송 기록. id가 같거나 같은 행사로 판정된 기록 → (id, 기록). 없으면 (None, None)."""
    if deal["id"] in events:
        return deal["id"], events[deal["id"]]
    info = info_of(deal)
    for eid, rec in events.items():
        if same_event(rec.get("info"), info):
            return eid, rec
    return None, None


def rekey(deals, events):
    """id가 바뀐 행사의 기록을 지금 id로 옮기고 확인된 정보를 새로 고친다 (보낼 것이 없어도)."""
    events = dict(events)
    for d in deals:
        if d["id"] in events:
            continue
        eid, rec = record_for(d, events)
        if eid:
            events.pop(eid)
            events[d["id"]] = {"info": info_of(d), "kinds": rec.get("kinds", {})}
    return events


# ---------------------------------------------------------------- 알림 대상

def due_kinds(deal, today, data_fresh, started):
    """지금 알릴 수 있는 종류 (보냈는지는 아직 보지 않는다)."""
    st = display_status(deal, today)
    if st in ("ended", "stale") or deal.get("from_icn") == "no":
        return []
    kinds = []
    dates_ok = "sale" not in (deal.get("conflicts") or [])  # 출처 간 판매 날짜가 다르면 날짜 알림을 하지 않는다
    start, end = _d(deal.get("sale_start")), _d(deal.get("sale_end"))
    if dates_ok and start:
        left = (start - today).days
        if left == 0:
            kinds.append("start_today")
        elif left == 1:
            kinds.append("upcoming_d1")
        elif left in (2, 3):
            kinds.append("upcoming_d3")
    if dates_ok and end and st == "live":
        left = (end - today).days
        if left == 0:
            kinds.append("closing_today")
        elif left == 1:
            kinds.append("closing_tomorrow")
    seen = _dt(deal.get("first_seen"))
    if data_fresh and seen and seen.date() >= today - timedelta(days=NEW_MAX_AGE_DAYS) and (not started or seen > _dt(started)):
        kinds.append("new")
    return kinds


def allowed_kinds(slot, today, slots_log):
    """이 시간대에 보낼 종류. 오늘 앞 시간대가 보내지 못했으면 그 종류도 더한다 (예약 지연·누락 보완)."""
    names = [s[0] for s in SLOTS]
    out = list(SLOT_KINDS[slot])
    done = slots_log.get(today.isoformat(), {})
    for prev in names[:names.index(slot)]:
        if done.get(prev) != "sent":
            out += [k for k in SLOT_KINDS[prev] if k not in out]
    return out


def plan(deals, state, now, data_fresh):
    """→ (보낼 항목 [(행사, 보여 줄 종류, 기록할 종류들, 기록 id)], 시간대). 시간대 밖이거나 이미 보낸 시간대면 빈 목록."""
    today = now.date()
    slot = slot_of(now)
    if not slot:
        return [], None
    if state.get("slots", {}).get(today.isoformat(), {}).get(slot) == "sent":
        return [], slot
    allowed = allowed_kinds(slot, today, state.get("slots", {}))
    events = state.get("events", {})
    items, taken = [], set()
    for d in deals:
        kinds = [k for k in due_kinds(d, today, data_fresh, state.get("started", "")) if k in allowed]
        if not kinds:
            continue
        eid, rec = record_for(d, events)
        sent = (rec or {}).get("kinds", {})
        todo = [k for k in kinds if k not in sent]
        # 행사를 새로 찾았는데 이미 날짜 알림을 받은 행사면 신규로 또 알리지 않는다
        if "new" in todo and sent:
            todo.remove("new")
        if not todo or (eid or d["id"]) in taken:
            continue
        taken.add(eid or d["id"])
        show = next(k for k in KIND_ORDER if k in todo)
        items.append((d, show, todo, eid or d["id"]))
    # 같은 종류 안에서는 공식 확인 먼저, 그다음 마감 가까운 순
    items.sort(key=lambda x: (KIND_ORDER.index(x[1]), x[0].get("verification") != "official", x[0].get("sale_end") or "9999"))
    return items, slot


# ---------------------------------------------------------------- 메시지

def source_label(deal):
    if deal.get("verification") == "official":
        return "판매처 공식" if deal.get("kind") == "platform" or deal.get("section") == "hotel" else "항공사 공식"
    return "기사 기준"


def item_text(deal, kind, today):
    e = html.escape
    hotel = deal.get("section") == "hotel"
    where = " · ".join((deal.get("regions") or [])[:2]) if hotel else " · ".join(_places(deal)[:2])
    name = deal.get("event_name") or deal.get("headline") or ""
    title = where or (name if len(name) <= 40 else name[:39].rstrip() + "…")
    lines = [f"<b>{e(deal.get('airline') or '')} · {e(title)}</b>"]
    if where and deal.get("event_name"):
        lines.append(e(deal["event_name"][:50]))
    lines.append(e(deal["discount"]) if deal.get("discount") else "할인 조건 확인 필요")
    start, end = deal.get("sale_start"), deal.get("sale_end")
    if kind in ("upcoming_d3", "upcoming_d1"):
        left = (date.fromisoformat(start) - today).days
        lines.append(f"{md(start)} 판매 시작 · D-{left}" + (f" · 마감 {md(end)}" if end else ""))
    elif kind in ("closing_today", "closing_tomorrow"):
        lines.append(f"판매 마감: {md(end)} ({'오늘' if kind == 'closing_today' else '내일'})")
    elif start or end:
        lines.append(f"판매 기간: {md(start) if start else ''}~{md(end) if end else ''}")
    else:
        lines.append("판매 기간: 확인 필요")
    src = f"확인 상태: {source_label(deal)}"
    if (deal.get("official_url") or "").startswith(("http://", "https://")):
        src += f' · <a href="{e(deal["official_url"], quote=True)}">공식 홈페이지</a>'
    lines.append(src)
    return "\n".join(lines)


def build_messages(items, slot, now, late=False):
    """→ [텍스트, …]. 길면 항목 경계에서 나눈다. 버튼은 보낼 때 붙인다."""
    if not items:
        return []
    today = now.date()
    counts = {}
    for _, k, _, _ in items:
        counts[k] = counts.get(k, 0) + 1
    head = ["✈️ <b>ICN 특가 레이더</b>", "", HEADER[slot], kr_date(today)]
    if late:
        head.append("앞 시간대 알림이 늦어 함께 보내 드려요.")
    head.append("")
    head += [f"{KIND_SUMMARY[k]} {counts[k]}건" for k in KIND_ORDER if k in counts]
    blocks, cur = [], None
    for d, k, _, _ in items:
        if k != cur:
            blocks.append(f"{RULE}\n\n{KIND_TITLE[k]}")
            cur = k
        blocks.append(item_text(d, k, today))
    tail = f"{RULE}\n\n{NOTE}"
    out, buf = [], "\n".join(head)
    for b in blocks:
        if len(buf) + len(b) + len(tail) + 4 > TEXT_MAX:
            out.append(buf)
            buf = "✈️ <b>ICN 특가 레이더</b> (이어서)"
        buf += "\n\n" + b
    out.append(buf + "\n\n" + tail)
    return out


# ---------------------------------------------------------------- 보내기

def send(token, chat_id, text, tries=5):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true",
               "reply_markup": json.dumps({"inline_keyboard": [[{"text": "전체 할인 행사 보기", "url": SITE}]]})}
    data = urllib.parse.urlencode(payload).encode()
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


def send_all(chats, text, send_one):
    """받는 사람 모두에게 동시에 보낸다 → 실패한 순번(1부터) 목록. 한 사람이라도 받았으면 보낸 것으로 친다
    (다시 보내면 받은 사람이 같은 알림을 또 받는다). 모두 실패하면 첫 오류를 낸다."""
    with ThreadPoolExecutor(max_workers=min(len(chats), 8) or 1) as pool:
        futures = [pool.submit(send_one, c, text) for c in chats]
    errors = [f.exception() for f in futures]
    failed = [i + 1 for i, e in enumerate(errors) if e]
    if chats and len(failed) == len(chats):
        raise errors[0]
    return failed


def migrate(state, deals):
    """예전 기록 {'started', 'sent': {id: 날짜, 'id:closing': 날짜, 'id:start': 날짜}} → 새 형식."""
    if "events" in state or "sent" not in state:
        return state
    by_id = {d["id"]: d for d in deals}
    events = {}
    for key, day in state["sent"].items():
        if key.startswith("failed:"):
            continue
        eid, _, kind = key.partition(":")
        rec = events.setdefault(eid, {"info": info_of(by_id[eid]) if eid in by_id else None, "kinds": {}})
        for k in {"": ["new"], "closing": ["closing_today", "closing_tomorrow"], "start": ["start_today"]}.get(kind, []):
            rec["kinds"][k] = day
    return {"started": state.get("started", ""), "events": events, "slots": {}}


def run(deals_data, state, now, sender, admin=None):
    """한 번 실행 → (새 state, 오류 또는 None). sender(text)가 예외를 내면 그 앞까지 보낸 항목만 기록하고,
    시간대는 '보냄'으로 표시하지 않아 남은 항목을 다음 실행에서 다시 보낸다."""
    deals = deals_data.get("deals", [])
    state = migrate(state, deals)
    today = now.date()
    if not state.get("started"):
        # 처음: 지금 있는 행사는 신규로 보지 않는다 (수십 건이 한꺼번에 오지 않게)
        state = {"started": now.isoformat(), "events": {}, "slots": {}}
    generated = deals_data.get("generated_at")
    age_h = (now - _dt(generated)).total_seconds() / 3600 if generated else 999
    data_fresh = age_h <= DATA_STALE_HOURS
    if not data_fresh:
        msg = f"행사 데이터가 {age_h:.0f}시간 전 것이라 신규 알림을 보내지 않습니다 (수집 확인 필요)."
        print(f"::warning::{msg}")
        if admin and state.get("admin_stale") != today.isoformat():
            admin(msg)
            state = {**state, "admin_stale": today.isoformat()}
    failed = (deals_data.get("stats") or {}).get("failed_queries") or 0
    if failed:
        print(f"::warning::직전 수집에서 뉴스 검색어 {failed}개가 실패했습니다.")
        if admin and state.get("admin_failed") != today.isoformat():
            admin(f"직전 수집에서 뉴스 검색어 {failed}개가 실패했습니다.")
            state = {**state, "admin_failed": today.isoformat()}

    state = {**state, "events": rekey(deals, state.get("events", {}))}
    items, slot = plan(deals, state, now, data_fresh)
    if not slot:
        print("[notify] 알림 시간대(09~21시)가 아니라 보내지 않습니다.")
        return state, None
    if not items:
        if state.get("slots", {}).get(today.isoformat(), {}).get(slot) == "sent":
            print(f"[notify] {slot}: 이 시간대는 이미 보냈습니다. 새 항목은 다음 시간대에 보냅니다.")
            return state, None
        print(f"[notify] {slot}: 보낼 항목이 없습니다.")
        return _mark_slot(state, today, slot, "empty"), None
    late = any(k not in SLOT_KINDS[slot] for _, _, todo, _ in items for k in todo)
    texts = build_messages(items, slot, now, late)
    # 여러 메시지로 나뉘면 메시지마다 그 안의 항목을 기록한다 (중간에 실패해도 보낸 것은 다시 보내지 않게)
    events = dict(state.get("events", {}))
    per_text = _split_items(items, texts)
    error = None
    for text, chunk in zip(texts, per_text):
        try:
            sender(text)
        except Exception as e:
            error = e
            break
        for d, _, todo, eid in chunk:
            rec = events.get(eid) or {"info": None, "kinds": {}}
            kinds = {**rec.get("kinds", {}), **{k: today.isoformat() for k in todo}}
            # 같은 행사로 판정된 예전 id 기록은 지금 id로 옮긴다
            events.pop(eid, None)
            events[d["id"]] = {"info": info_of(d), "kinds": kinds}
    state = {**state, "events": _prune(events, today)}
    if error:
        return state, error
    print(f"[notify] {slot}: 항목 {len(items)}건을 메시지 {len(texts)}통으로 보냈습니다.")
    return _mark_slot(state, today, slot, "sent"), None


def _split_items(items, texts):
    """build_messages가 나눈 메시지마다 들어간 항목 (제목 줄로 세어 나눈다)."""
    if len(texts) == 1:
        return [items]
    out, i = [], 0
    for t in texts:
        n = t.count("확인 상태:")
        out.append(items[i:i + n])
        i += n
    return out


def _mark_slot(state, today, slot, value):
    slots = {k: v for k, v in state.get("slots", {}).items() if k >= (today - timedelta(days=7)).isoformat()}
    slots[today.isoformat()] = {**slots.get(today.isoformat(), {}), slot: value}
    return {**state, "slots": slots}


def _prune(events, today):
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    return {k: v for k, v in events.items() if max(v.get("kinds", {}).values() or ["0"]) >= cutoff}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 메시지만 출력")
    ap.add_argument("--now", help="시험용 현재 시각 (KST, 예: 2026-10-27T09:10)")
    args = ap.parse_args(argv)
    dry = args.dry_run or os.environ.get("DRY_RUN") == "1"
    now = datetime.fromisoformat(args.now).replace(tzinfo=KST) if args.now else datetime.now(KST)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    admin_chat = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    if not dry and (not token or not chats):
        print("텔레그램 비밀값이 없어 알림을 건너뜁니다.")
        return 0
    deals_data = json.loads(DEALS.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}

    def sender(text):
        if dry:
            print("----- 메시지 -----\n" + text + "\n[버튼: 전체 할인 행사 보기]")
            return
        failed = send_all(chats, text, lambda c, t: send(token, c, t))
        if failed:
            # chat id는 찍지 않고 TELEGRAM_CHAT_ID 안의 순번만 남긴다
            note = f"받는 사람 {', '.join(f'{n}번째' for n in failed)}에게 보내지 못했습니다 (번호가 틀렸거나 봇을 차단했을 수 있음)."
            print(f"::warning::{note}")
            admin(note)

    def admin(text):
        if dry:
            print("----- 관리자 -----\n" + text)
        elif token and admin_chat:
            send(token, admin_chat, "[관리자] " + text)

    new_state, error = run(deals_data, state, now, sender, admin)
    if error:
        # 토큰·chat id는 찍지 않는다
        print(f"::error::텔레그램 발송 실패: {type(error).__name__} {getattr(error, 'code', '')} — 남은 항목은 다음 실행에서 보냅니다.")
    if dry:
        print("[dry-run] 기록 파일은 바꾸지 않았습니다.")
        return 0
    # 실패해도 그 앞까지 보낸 기록은 저장한다 (다시 보내지 않게). saved_at은 저장소 파일과 Actions 캐시 중
    # 어느 쪽이 최신인지 가리는 데 쓴다 (기록을 저장소에 못 올린 경우 캐시 쪽이 더 최신, telegram.yml)
    # 바뀐 게 없으면 파일을 그대로 둔다 (실행마다 저장 시각만 바뀐 커밋이 쌓이지 않게)
    if {k: v for k, v in new_state.items() if k != "saved_at"} == {k: v for k, v in state.items() if k != "saved_at"}:
        return 1 if error else 0
    new_state = {**new_state, "saved_at": datetime.now(KST).isoformat(timespec="seconds")}
    STATE.write_text(json.dumps(new_state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
