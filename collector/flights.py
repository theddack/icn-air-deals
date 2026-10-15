"""인천공항 출발 시간표 수집: python -m collector.flights

data/flights.json  화면의 '출발 시간표' 탭이 읽는 파일

출처 (공공데이터포털, 인천국제공항공사, 키는 환경변수 DATA_GO_KR_KEY)
- 여객기 정기운항편 일정  PaxFltSched/getPaxFltSchedDepartures
    편명·항공사·출발 예정 시각(HHMM)·도착 공항·운항 시작/종료일·요일(Y/N). 시즌(S26 등) 단위.
    2026-10-15 확인: 날짜·공항 파라미터를 줘도 전체가 오고, 도착 시각 필드는 없다.
- 항공기 운항 현황 상세    statusOfAllFltDeOdp/getFltDeparturesDeOdp
    오늘 앞뒤 며칠(2026-10-15 확인: 3일 전 ~ 6일 뒤)의 편별 예정·변경 시각과 상태(출발·지연 등).

시각은 모두 인천공항 기준 한국 시각(KST)이다. 정기 일정은 '예정'이고, 운항 현황이 있는 날짜만 변경 시각·상태를 붙인다.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta

from .status import KST

BASE = "https://apis.data.go.kr/B551177/"
SCHEDULE = "PaxFltSched/getPaxFltSchedDepartures"
STATUS = "statusOfAllFltDeOdp/getFltDeparturesDeOdp"
UA = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MAX_PAGES = 30


class ApiError(Exception):
    pass


def _call(key, path, page):
    q = urllib.parse.urlencode({"serviceKey": key, "type": "json", "numOfRows": 1000, "pageNo": page})
    req = urllib.request.Request(BASE + path + "?" + q, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # 오류 본문에는 키가 없지만, 혹시 몰라 지운다
        raise ApiError(f"{path} HTTP {e.code}: {e.read().decode('utf-8', 'replace').replace(key, '***')[:200]}") from None
    try:
        data = json.loads(body)
        b = data["response"]["body"]
    except (ValueError, KeyError):
        raise ApiError(f"{path} 응답 형식 오류: {body.replace(key, '***')[:200]}") from None
    items = b.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", [])
    return b.get("totalCount") or 0, items if isinstance(items, list) else [items]


def fetch_all(key, path):
    out, page = [], 1
    while page <= MAX_PAGES:
        total, items = _call(key, path, page)
        out += items
        if not items or len(out) >= total:
            return out
        page += 1
    return out


def _d(yyyymmdd):
    return date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))


def _hhmm(s):
    s = str(s or "")
    return f"{s[:2]}:{s[2:4]}" if len(s) == 4 and s.isdigit() else None


def normalize_schedule(items):
    """정기 일정 → [{flight, airline, time, dest_code, dest, first, last, days('1111100' 월~일), season}]"""
    rows = []
    for it in items:
        t = _hhmm(it.get("st"))
        try:
            first, last = _d(str(it["firstdate"])), _d(str(it["lastdate"]))
        except (KeyError, ValueError):
            continue
        if not (t and it.get("flightid")):
            continue
        rows.append({
            "flight": it["flightid"], "airline": it.get("airline"), "time": t,
            "dest_code": it.get("airportcode"), "dest": it.get("airport"),
            "first": first.isoformat(), "last": last.isoformat(),
            "days": "".join("1" if str(it.get(d, "")).upper() == "Y" else "0" for d in DAYS),
            "season": it.get("season"),
        })
    rows.sort(key=lambda r: (r["time"], r["flight"]))
    return rows


def coverage(rows, today):
    """조회 가능한 날짜 범위. full_until은 정기편 대부분(종료일 최빈값)이 끝나는 날,
    partial_until은 가장 늦게 끝나는 편의 종료일. full_until 뒤는 일부 편만 있다."""
    if not rows:
        return None
    lasts = Counter(r["last"] for r in rows)
    full = lasts.most_common(1)[0][0]
    return {"from": today.isoformat(), "full_until": full, "partial_until": max(lasts)}


def normalize_status(items):
    """운항 현황 → {날짜: {편명: {estimated, remark, gate, codeshare_of}}} — 여객편만."""
    out = {}
    for it in items:
        if it.get("passengerOrCargo") not in (None, "Passenger"):
            continue
        sched = str(it.get("scheduleDatetime") or "")
        if len(sched) != 12 or not it.get("flightId"):
            continue
        day = f"{sched[:4]}-{sched[4:6]}-{sched[6:8]}"
        est = str(it.get("estimatedDatetime") or "")
        out.setdefault(day, {})[it["flightId"]] = {
            "scheduled": f"{sched[8:10]}:{sched[10:12]}",
            "estimated": f"{est[8:10]}:{est[10:12]}" if len(est) == 12 else None,
            "estimated_day": f"{est[:4]}-{est[4:6]}-{est[6:8]}" if len(est) == 12 else None,
            "remark": it.get("remark"),
            "gate": it.get("gateNumber"),
            # 공동운항 편명(Slave)은 실제 운항편(masterFlightId)을 가리킨다
            "codeshare_of": it.get("masterFlightId") if it.get("codeshare") == "Slave" else None,
        }
    return out


def flights_on(rows, day):
    """그 날짜(date)에 운항하는 정기편 목록."""
    iso, wd = day.isoformat(), day.weekday()
    return [r for r in rows if r["first"] <= iso <= r["last"] and r["days"][wd] == "1"]


def build(schedule_items, status_items, now):
    today = now.date()
    rows = normalize_schedule(schedule_items)
    status = normalize_status(status_items)
    status_days = sorted(status)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "timezone": "KST (인천공항 현지 시각)",
        "sources": {
            "schedule": "인천국제공항공사 여객기 정기운항편 일정 (공공데이터포털)",
            "status": "인천국제공항공사 항공기 운항 현황 상세 (공공데이터포털)",
        },
        "coverage": coverage(rows, today),
        "status_range": {"from": status_days[0], "to": status_days[-1]} if status_days else None,
        "seasons": sorted({r["season"] for r in rows if r["season"]}),
        "schedule": rows,
        "status": status,
    }


def main():
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        print("[flights] DATA_GO_KR_KEY 없음 — 시간표 수집을 건너뜁니다.", file=sys.stderr)
        return 0
    now = datetime.now(KST)
    try:
        sched = fetch_all(key, SCHEDULE)
    except (ApiError, OSError) as e:
        # 실패하면 이전 flights.json을 그대로 두고, 화면은 마지막 수집 시각으로 오래됨을 알린다
        print(f"[flights] 정기 일정 수집 실패, 이전 데이터 유지: {e}", file=sys.stderr)
        return 0
    try:
        status = fetch_all(key, STATUS)
    except (ApiError, OSError) as e:
        print(f"[flights] 운항 현황 수집 실패, 정기 일정만 저장: {e}", file=sys.stderr)
        status = []
    data = build(sched, status, now)
    data["status_failed"] = not status
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "flights.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    cov = data["coverage"] or {}
    print(f"[flights] 정기편 {len(data['schedule'])}건 (전체 {cov.get('full_until')}까지, 일부 {cov.get('partial_until')}까지), "
          f"운항 현황 {sum(len(v) for v in data['status'].values())}건 {data['status_range']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
