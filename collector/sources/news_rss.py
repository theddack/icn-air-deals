"""Google 뉴스 RSS 검색으로 항공사 특가·호텔 숙박 할인 기사를 모은다."""

import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from ..airlines import AIRLINES
from ..hotels import HOTELS
from ..status import KST

RSS_URL = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
RSS_URL_EN = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
USER_AGENT = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"
WINDOW = "when:30d"
GENERIC_QUERIES = [
    f"인천 출발 항공권 특가 {WINDOW}",
    f"항공권 프로모션 국제선 {WINDOW}",
    # 국내선: 항공사 이름 검색에서 빠지는 노선 중심 기사 (제목에 항공사가 있어야 수집된다)
    f"국내선 항공권 특가 {WINDOW}",
    f"김포 제주 항공권 할인 {WINDOW}",
]


# 해외 호텔 시범(2026-10-15): 국내 업체·언론이 다루는 해외 숙박 할인
OVERSEAS_HOTEL_QUERIES = [f"해외 호텔 할인 {WINDOW}", f"해외 호텔 특가 {WINDOW}", f"해외 숙소 할인 {WINDOW}", f"해외 리조트 특가 {WINDOW}"]
# 영어 뉴스 시범: 번역하지 않고 가격 할인이 분명한 제목만 받는다 (extract.is_hotel_sale_en)
EN_QUERIES = [f"hotel sale percent off {WINDOW}", f"hotel flash sale {WINDOW}", f"resort discount code {WINDOW}",
              f"Accor sale {WINDOW}", f"Club Med discount {WINDOW}", f"Agoda sale {WINDOW}", f"Trip.com hotel sale {WINDOW}",
              f"Marriott sale off {WINDOW}", f"Hilton sale off {WINDOW}", f"Asia hotel deals sale {WINDOW}"]


def queries():
    """(검색어, 언어) 목록"""
    for q in _ko_queries():
        yield q, "ko"
    for q in EN_QUERIES:
        yield q, "en"


def _ko_queries():
    for a in AIRLINES:
        for name in a.get("search", [a["name"]]):
            yield f'"{name}" (특가 OR 프로모션 OR 할인 OR 세일) {WINDOW}'
    yield from GENERIC_QUERIES
    for h in HOTELS:
        for name in h.get("search", [h["name"]]):
            yield f'"{name}" (특가 OR 할인 OR 세일 OR 프로모션 OR 쿠폰) {WINDOW}'
    yield from OVERSEAS_HOTEL_QUERIES


def fetch(query, timeout=20, lang="ko"):
    url = (RSS_URL_EN if lang == "en" else RSS_URL).format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def parse(xml_bytes, lang="ko"):
    """RSS → [{'title', 'outlet', 'url', 'published'(KST ISO date)}]"""
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        pub = it.findtext("pubDate")
        if not pub:
            continue
        out.append({
            "raw_title": it.findtext("title") or "",
            "outlet": it.findtext("source"),
            "url": it.findtext("link"),
            "published": parsedate_to_datetime(pub).astimezone(KST).date().isoformat(),
            "lang": lang,
        })
    return out


def collect(delay=1.0):
    """모든 검색어를 돌려 기사 목록과 실패한 검색어 수를 돌려준다."""
    items, failed = [], 0
    qs = list(queries())
    for i, (q, lang) in enumerate(qs):
        try:
            items.extend(parse(fetch(q, lang=lang), lang))
        except Exception as e:  # 검색어 하나 실패로 전체를 멈추지 않는다
            failed += 1
            print(f"[rss] 실패: {q!r}: {e}", file=sys.stderr)
        if i < len(qs) - 1:
            time.sleep(delay)
    return items, failed, len(qs)
