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
import time
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
# 2026-10-17~20 Actions 실행 24번 중 운항 현황 3번(503·TLS 시간 초과), 정기 일정 1번(시간 초과)이 한 번에 실패했다.
# 일시 오류라서 잠깐 쉬고 다시 묻는다. 4xx(키·파라미터 오류)는 다시 물어도 같아서 바로 실패로 둔다
RETRY_WAITS = (5, 20)


class ApiError(Exception):
    def __init__(self, msg, retryable=False):
        super().__init__(msg)
        self.retryable = retryable


def _call(key, path, page):
    for wait in RETRY_WAITS + (None,):
        try:
            return _call_once(key, path, page)
        except ApiError as e:
            if wait is None or not e.retryable:
                raise
        except OSError:
            if wait is None:
                raise
        time.sleep(wait)


def _call_once(key, path, page):
    q = urllib.parse.urlencode({"serviceKey": key, "type": "json", "numOfRows": 1000, "pageNo": page})
    req = urllib.request.Request(BASE + path + "?" + q, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # 오류 본문에는 키가 없지만, 혹시 몰라 지운다
        raise ApiError(f"{path} HTTP {e.code}: {e.read().decode('utf-8', 'replace').replace(key, '***')[:200]}",
                       retryable=e.code >= 500 or e.code == 429) from None
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


SEASON_FILLED = 0.8  # 새 시즌 첫 주 운항편이 이전 시즌 마지막 날의 이 비율 이상이면 새 시즌 일정이 다 나온 것으로 본다


def _mode(values):
    return Counter(values).most_common(1)[0][0]


def coverage(rows, today):
    """조회 가능한 날짜 범위. full_until은 정기편 대부분(종료일 최빈값)이 끝나는 날,
    partial_until은 가장 늦게 끝나는 편의 종료일. full_until 뒤는 일부 편만 있다.

    시즌이 둘(예: 하계 S26 + 동계 W26)이면 새 시즌이 이전 시즌만큼 채워졌는지 운항편 수로 본다. 다 채워졌으면
    새 시즌 종료일까지 확보. 2026-10-23: 동계 공개 뒤에도 전체 최빈값이 하계 종료일(10/24)이라 10/25부터
    '미확보'로 보일 뻔했다 (10/24 실제 운항 553편, 동계 첫 주 544~551편)."""
    if not rows:
        return None
    lasts = Counter(r["last"] for r in rows)
    full = lasts.most_common(1)[0][0]
    seasons = {}
    for r in rows:
        if r.get("season"):
            seasons.setdefault(r["season"], []).append(r)
    if len(seasons) >= 2:
        order = sorted(seasons, key=lambda k: _mode(r["first"] for r in seasons[k]))
        prev, new = seasons[order[-2]], seasons[order[-1]]
        prev_end = date.fromisoformat(_mode(r["last"] for r in prev))
        real = [r for r in rows if not r.get("codeshare_of")]
        before = len(flights_on(real, prev_end))
        after = min(len(flights_on(real, prev_end + timedelta(days=i))) for i in range(1, 8))
        full = _mode(r["last"] for r in new) if before and after >= SEASON_FILLED * before else prev_end.isoformat()
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
            "estimated": f"{est[8:10]}:{est[10:12]}" if len(est) == 12 else None,
            "estimated_day": f"{est[:4]}-{est[4:6]}-{est[6:8]}" if len(est) == 12 else None,
            "remark": it.get("remark"),
            # 공동운항 편명(Slave)은 실제 운항편(masterFlightId)을 가리킨다
            "codeshare_of": it.get("masterFlightId") if it.get("codeshare") == "Slave" else None,
        }
    return out


def flights_on(rows, day):
    """그 날짜(date)에 운항하는 정기편 목록."""
    iso, wd = day.isoformat(), day.weekday()
    return [r for r in rows if r["first"] <= iso <= r["last"] and r["days"][wd] == "1"]


def mark_codeshares(rows, status):
    """정기 일정에는 공동운항 구분이 없다. 운항 현황에서 한 번이라도 공동운항 편명(Slave)으로 나온 편명이면
    정기 일정 행에도 실제 운항편을 붙인다. 현황에 안 나온 편은 None(모름)으로 둔다."""
    master_of = {}
    for day in status.values():
        for flight, s in day.items():
            if s["codeshare_of"]:
                master_of[flight] = s["codeshare_of"]
            elif flight not in master_of:
                master_of[flight] = None
    for r in rows:
        r["codeshare_of"] = master_of.get(r["flight"])
        r["status_seen"] = r["flight"] in master_of
    return rows


def reuse_previous(rows, previous, today):
    """운항 현황을 못 받았을 때 직전 파일의 현황(오늘 이후)과 공동운항 표시를 이어 쓴다.
    비워 두면 공동운항 판매 편명이 실제 운항편처럼 따로 보이고 지연·출발 상태가 사라진다."""
    marks = {r["flight"]: (r.get("codeshare_of"), r.get("status_seen", False)) for r in previous.get("schedule", [])}
    for r in rows:
        r["codeshare_of"], r["status_seen"] = marks.get(r["flight"], (None, False))
    return {d: v for d, v in (previous.get("status") or {}).items() if d >= today.isoformat()}


def build(schedule_items, status_items, now, previous=None):
    today = now.date()
    if not status_items and previous:
        rows = normalize_schedule(schedule_items)
        status = reuse_previous(rows, previous, today)
        out = _assemble(rows, status, now, today)
        out["status_from"] = previous.get("generated_at")
        return out
    status = normalize_status(status_items)
    rows = mark_codeshares(normalize_schedule(schedule_items), status)
    # 화면은 오늘부터만 고를 수 있으니 지난 날짜 현황은 싣지 않는다. 공동운항 편명은 위에서 정기편 행에 붙였으므로
    # 현황에는 실제 운항편(Master)만 남긴다. 둘 다 파일 크기 때문이다 (2026-10-15 기준 1.8MB → 약 0.6MB)
    status = {d: {k: v for k, v in day.items() if not v["codeshare_of"]}
              for d, day in status.items() if d >= today.isoformat()}
    return _assemble(rows, status, now, today)


def _assemble(rows, status, now, today):
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
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "flights.json")
    previous = None
    try:
        status = fetch_all(key, STATUS)
    except (ApiError, OSError) as e:
        status = []
        try:
            with open(path, encoding="utf-8") as f:
                previous = json.load(f)
        except (OSError, ValueError):
            pass
        print(f"[flights] 운항 현황 수집 실패, {'직전 현황을 이어 씀' if previous else '정기 일정만 저장'}: {e}", file=sys.stderr)
    data = build(sched, status, now, previous)
    data["status_failed"] = not status
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    cov = data["coverage"] or {}
    print(f"[flights] 정기편 {len(data['schedule'])}건 (전체 {cov.get('full_until')}까지, 일부 {cov.get('partial_until')}까지), "
          f"운항 현황 {sum(len(v) for v in data['status'].values())}건 {data['status_range']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
