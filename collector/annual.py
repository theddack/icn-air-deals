"""연례 세일 예고. 해마다 비슷한 때 열리는 세일이 곧 올 것 같으면 알려 준다 (2026-10-31).

- data/annual_sales.json: 직접 정리한 대표 연례 세일과 대략적인 시기 (지난 기사 기준)
- data/event_history.json: 수집할 때마다 판매 날짜가 확인된 행사를 쌓는다 (지우지 않고 EVENT_KEEP_YEARS년 보관).
  1년이 지나면 '작년 이맘때 열린 행사'를 이 기록으로 찾는다.
지금 그 항공사의 같은 행사가 이미 보이면(판매 중·예정) 예고하지 않는다.
"""

import re
from datetime import date, timedelta

from .status import display_status

AHEAD_DAYS = 14         # 오늘부터 이 일수 안에 시작할 것 같은 세일만
EVENT_KEEP_YEARS = 3


def _norm(s):
    return re.sub(r"[\s\W_]+", "", s or "").lower()


def remember(history, deals, today):
    """판매 시작일이 확인된 행사를 기록에 더한다 → 새 기록."""
    events = dict((history or {}).get("events") or {})
    for d in deals:
        if not d.get("sale_start") or "sale" in (d.get("conflicts") or []) or d.get("airline_id") in (None, "multi"):
            continue
        name = d.get("event_name") or d.get("headline") or ""
        key = f"{d['airline_id']}|{d['sale_start']}|{_norm(name)[:24]}"
        events[key] = {"airline_id": d["airline_id"], "airline": d.get("airline") or "", "name": name[:60],
                       "sale_start": d["sale_start"], "sale_end": d.get("sale_end")}
    cutoff = date(today.year - EVENT_KEEP_YEARS, today.month, 1).isoformat()
    events = {k: v for k, v in sorted(events.items()) if v["sale_start"] >= cutoff}
    return {"about": "판매 날짜가 확인된 행사 기록 (collector/annual.py). 연례 세일 예고에 쓴다.", "events": events}


def _this_year(md, today):
    """'MM-DD' → 오늘 이후 가장 가까운 그 날짜 (지났으면 내년)."""
    m, d = map(int, md.split("-"))
    try:
        day = date(today.year, m, d)
    except ValueError:  # 2월 29일
        day = date(today.year, m, 28)
    return day if day >= today else day.replace(year=today.year + 1)


def _shown(deals, airline_id, words, today):
    """그 항공사의 같은 행사가 지금 보이면(마감·오래된 것 제외) True."""
    for d in deals:
        if d.get("airline_id") != airline_id or display_status(d, today) in ("ended", "stale"):
            continue
        hay = _norm((d.get("event_name") or "") + (d.get("headline") or ""))
        if any(_norm(w) and _norm(w) in hay for w in words):
            return True
    return False


def expected(seed, history, deals, today, ahead=AHEAD_DAYS):
    """→ [{airline, name, start, basis}] 시작이 가까운 순. start는 올해 예상 시작일(대략)."""
    out, seen = [], set()
    until = today + timedelta(days=ahead)
    for s in (seed or {}).get("sales") or []:
        for w in s.get("windows") or []:
            start = _this_year(w["from"], today)
            if not (today < start <= until) or _shown(deals, s["airline_id"], s.get("keywords") or [s["name"]], today):
                continue
            years = sorted({y[:4] for y in w.get("seen") or []})
            out.append({"airline": s["airline"], "name": s["name"], "start": start.isoformat(),
                        "basis": "지난 " + "·".join(years) + "년 기사 기준" if years else "지난 기사 기준"})
            seen.add((s["airline_id"], _norm(s["name"])))
    for e in ((history or {}).get("events") or {}).values():
        last = date.fromisoformat(e["sale_start"])
        try:
            start = last.replace(year=last.year + 1)
        except ValueError:
            start = last.replace(year=last.year + 1, day=28)
        name = e["name"]
        if not (today < start <= until) or (e["airline_id"], _norm(name)) in seen:
            continue
        if any(a == e["airline_id"] and (n in _norm(name) or _norm(name) in n) for a, n in seen):
            continue
        if _shown(deals, e["airline_id"], [name[:12]], today):
            continue
        out.append({"airline": e["airline"], "name": name, "start": start.isoformat(), "basis": f"{last.year}년 기록 기준"})
        seen.add((e["airline_id"], _norm(name)))
    out.sort(key=lambda x: x["start"])
    return out
