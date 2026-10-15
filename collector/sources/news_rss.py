"""Google 뉴스 RSS 검색으로 항공사 특가 기사를 모은다."""

import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from ..airlines import AIRLINES
from ..status import KST

RSS_URL = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
USER_AGENT = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"
WINDOW = "when:30d"
GENERIC_QUERIES = [
    f"인천 출발 항공권 특가 {WINDOW}",
    f"항공권 프로모션 국제선 {WINDOW}",
]


def queries():
    for a in AIRLINES:
        for name in a.get("search", [a["name"]]):
            yield f'"{name}" (특가 OR 프로모션 OR 할인 OR 세일) {WINDOW}'
    yield from GENERIC_QUERIES


def fetch(query, timeout=20):
    url = RSS_URL.format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()


def parse(xml_bytes):
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
        })
    return out


def collect(delay=1.0):
    """모든 검색어를 돌려 기사 목록과 실패한 검색어 수를 돌려준다."""
    items, failed = [], 0
    qs = list(queries())
    for i, q in enumerate(qs):
        try:
            items.extend(parse(fetch(q)))
        except Exception as e:  # 검색어 하나 실패로 전체를 멈추지 않는다
            failed += 1
            print(f"[rss] 실패: {q!r}: {e}", file=sys.stderr)
        if i < len(qs) - 1:
            time.sleep(delay)
    return items, failed, len(qs)
