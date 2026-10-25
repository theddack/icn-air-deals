"""땡처리닷컴 판매 중인 땡처리 항공권 중 인천 출발 → data/ttang.json (하루 1번).

python -m collector.ttang

- 판매 목록(SOURCE) 한 페이지를 하루 한 번(KST) 받는다. robots.txt(2026-10-25 확인)는 이름 있는 검색 봇에만
  /html·/view 등을 막고 이 경로와 일반 봇은 막지 않는다. 봇임을 밝힌 User-Agent를 쓴다.
- 이용약관은 회사 정보를 사전 승낙 없이 '영리목적으로 이용'하는 것만 금지한다. 이 사이트는 비영리이고
  노선·항공사·원화 총액·출발 기간과 원문(목록) 링크만 보여준다.
- 판매 상품 목록이라 매일 통째로 바꾼다(지난 상품은 남기지 않는다). 가격은 수집 시각 기준 표시 총액이며
  좌석·날짜에 따라 달라질 수 있다.
- 실패하거나 0건이면 이전 파일을 두고 다음 수집 때 다시 시도한다 (행사 수집·배포는 계속).
"""

import html
import json
import re
import sys
import urllib.request
from pathlib import Path

from .status import KST, today_kst

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ttang.json"
LIST_URL = "https://www.ttang.com/ttangair/search/ttang/list.do?arr0=A2ALL&dep0=ICN&orderBy=LOW_COST"
SOURCE = LIST_URL + "&scale=200&page=1"  # 한 번에 전부 (2026-10-25: 출발지 섞여 164건, 인천 114건)
USER_AGENT = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"

_ROW = re.compile(r'<tr>\s*(<td><p class="shortCut">.*?)</tr>', re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_DATA = re.compile(r'data-([a-zA-Z]+)="([^"]*)"')
_PRICE = re.compile(r"([\d,]+)\s*원")
_RANGE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{4})\.(\d{2})\.(\d{2})")


def _text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse(page):
    """목록 HTML → 인천 출발 상품 목록 (가격 낮은 순)."""
    out = []
    for row in _ROW.findall(page):
        tds = _TD.findall(row)
        data = dict(_DATA.findall(row))
        if len(tds) < 7 or data.get("depCity") != "ICN":
            continue
        price = _PRICE.search(_text(tds[6]))
        dates = _RANGE.search(_text(tds[4]))
        if not price or not dates:
            continue
        y1, m1, d1, y2, m2, d2 = dates.groups()
        out.append({
            "destination": _text(tds[1]), "dest_code": data.get("arrCity") or None,
            "airline": _text(tds[2]), "airline_code": data.get("airlineCode") or None,
            "direct": _text(tds[3]) == "직항", "trip": "oneway" if _text(tds[5]) == "편도" else "roundtrip",
            "depart_from": f"{y1}-{m1}-{d1}", "depart_to": f"{y2}-{m2}-{d2}",
            "price": int(price.group(1).replace(",", "")),
        })
    return sorted(out, key=lambda x: (x["price"], x["destination"]))


def fetch():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", "replace")


def main(today=None, now=None):
    from datetime import datetime
    today = today or today_kst()
    prev = {}
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        pass
    if prev.get("fetched_on") == today.isoformat():
        print("[ttang] 오늘 이미 받았습니다. 건너뜁니다.")
        return 0
    try:
        items = parse(fetch())
    except Exception as e:  # 사이트 문제로 배포를 멈추지 않는다
        print(f"[ttang] 실패: {type(e).__name__} {e}", file=sys.stderr)
        return 0
    if not items:
        # 페이지 구조가 바뀌었거나 막혔을 수 있다. 오늘 받은 것으로 치지 않고 언제부터 비었는지만 남긴다
        prev["empty_since"] = prev.get("empty_since") or today.isoformat()
        OUT.write_text(json.dumps(prev, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"[ttang] 인천 출발 0건 ({prev['empty_since']}부터) — 다음 수집 때 다시 시도합니다.", file=sys.stderr)
        return 0
    now = now or datetime.now(KST)
    OUT.write_text(json.dumps({"fetched_on": today.isoformat(), "fetched_at": now.isoformat(timespec="minutes"),
                               "source": LIST_URL, "items": items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[ttang] 인천 출발 땡처리 항공권 {len(items)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
