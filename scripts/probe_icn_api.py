"""인천공항 공공 API 응답 구조 확인 (v3 4단계 사전 검증). 키는 출력하지 않는다.

python -m scripts.probe_icn_api   # 환경변수 DATA_GO_KR_KEY 필요
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

KEY = os.environ["DATA_GO_KR_KEY"]
BASE = "https://apis.data.go.kr/B551177/"
UA = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"


def call(path, **params):
    q = urllib.parse.urlencode({"serviceKey": KEY, "type": "json", **params})
    req = urllib.request.Request(BASE + path + "?" + q, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        body, status = e.read().decode("utf-8", "replace"), e.code
    body = body.replace(KEY, "***")
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body[:300]


def items_of(data):
    b = data["response"]["body"]
    items = b.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", [])
    return b.get("totalCount"), items if isinstance(items, list) else [items]


def all_items(path, **params):
    out, page = [], 1
    while True:
        status, data = call(path, numOfRows=1000, pageNo=page, **params)
        if not isinstance(data, dict) or "response" not in data:
            print("  응답 오류", status, data)
            return out
        total, items = items_of(data)
        out += items
        if not items or len(out) >= (total or 0) or page >= 20:
            return out
        page += 1


def summarize(name, items, date_fields):
    print(f"\n## {name}: {len(items)}건")
    if not items:
        return
    keys = Counter(k for it in items for k in it)
    print("  필드(등장 횟수):", dict(keys))
    print("  첫 항목:", json.dumps(items[0], ensure_ascii=False))
    for f in date_fields:
        vals = sorted(str(it[f]) for it in items if it.get(f))
        if vals:
            print(f"  {f}: 최소 {vals[0]} / 최대 {vals[-1]} / 서로 다른 값 {len(set(vals))}개, 상위 {Counter(vals).most_common(5)}")


print("=== 여객기 정기운항편 일정 (출발) ===")
sched = all_items("PaxFltSched/getPaxFltSchedDepartures")
summarize("기본 호출", sched, ["firstdate", "lastdate", "st"])
# 요일 필드가 있으면 분포를 본다
for k in ("monday", "mon", "operationDays", "day", "weekday"):
    if sched and k in sched[0]:
        print(f"  요일 필드 {k}:", Counter(str(it.get(k)) for it in sched).most_common(5))
# 동계(10/25~) 일정이 있는지: 날짜 범위로 걸러 본다
win = [it for it in sched if str(it.get("lastdate", "")) > "20261024"]
print(f"  운항 종료일이 10/24 이후인 편: {len(win)}건")
# 검색 파라미터 지원 여부 (문서 확인 전 시험)
for params in ({"schDate": "20261120"}, {"searchday": "20261120"}, {"airport_code": "KIX"}, {"lang": "K"}):
    status, data = call("PaxFltSched/getPaxFltSchedDepartures", numOfRows=3, pageNo=1, **params)
    total = items_of(data)[0] if isinstance(data, dict) and "response" in data else data
    print(f"  파라미터 {params}: HTTP {status}, totalCount {total}")

print("\n=== 항공기 운항 현황 상세 (출발) ===")
status_items = all_items("statusOfAllFltDeOdp/getFltDeparturesDeOdp")
summarize("기본 호출", status_items, ["scheduleDatetime", "scheduleDateTime", "estimatedDatetime", "estimatedDateTime"])
if status_items:
    print("  운항 상태값:", Counter(str(it.get("remark")) for it in status_items).most_common(10))
    print("  공동운항 구분:", Counter(str(it.get("codeshare")) for it in status_items).most_common(5))
