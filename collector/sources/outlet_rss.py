"""언론사 자체 RSS에서 기사 요약문을 받아 사실값(날짜·노선·할인)만 뽑는다.

- robots.txt가 RSS를 허용하고 요약문을 주는 곳만 넣었다 (2026-10-15 확인). 머니투데이·파이낸셜뉴스·헤럴드경제는
  robots.txt가 막아서 뺐다.
- 요약문 전체는 공개 저장소에 저장하지 않는다. collector.extract.facts_from_summary가 뽑은 값과
  EVIDENCE_MAX자 이하의 근거 구절, 원문 기사 주소만 남긴다.
- 피드마다 최근 50~100건만 있어서 하루 4회 받으며 쌓아야 효과가 난다.
"""

import html
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from ..status import KST

USER_AGENT = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"
FEEDS = [
    ("싱글리스트", "https://www.slist.kr/rss/allArticle.xml"),
    ("국제뉴스", "https://www.gukjenews.com/rss/allArticle.xml"),
    ("ER 이코노믹리뷰", "https://www.econovill.com/rss/allArticle.xml"),
    ("신아일보", "https://www.shinailbo.co.kr/rss/allArticle.xml"),
    ("이로운뉴스", "https://www.eroun.net/rss/allArticle.xml"),
    ("핀포인트뉴스", "https://www.pinpointnews.co.kr/rss/allArticle.xml"),
    ("스트레이트뉴스", "https://www.straightnews.co.kr/rss/allArticle.xml"),
    ("시장경제신문", "https://www.meconomynews.com/rss/allArticle.xml"),
    ("한국면세뉴스", "https://www.kdfnews.com/rss/allArticle.xml"),
    ("트래블데일리", "https://www.traveldaily.co.kr/rss/allArticle.xml"),
    ("여행신문", "https://www.traveltimes.co.kr/rss/allArticle.xml"),
    ("투어코리아", "https://www.tournews21.com/rss/allArticle.xml"),
    ("여행레저신문", "https://www.tlnews.co.kr/rss/allArticle.xml"),
    ("뉴시스", "https://newsis.com/RSS/economy.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("이투데이", "https://rss.etoday.co.kr/eto/etoday_news_all.xml"),
    ("서울파이낸스", "https://www.seoulfn.com/rss/allArticle.xml"),
]


def _text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _pub(s):
    """RFC 822(대부분) 또는 'YYYY-MM-DD HH:MM:SS'(일부 언론사) → KST 날짜 ISO."""
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).astimezone(KST).date().isoformat()
    except (TypeError, ValueError):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s.strip())
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse(xml_bytes, outlet):
    out = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = _text(it.findtext("title"))
        if not title:
            continue
        out.append({"outlet": outlet, "title": title, "summary": _text(it.findtext("description")),
                    "url": (it.findtext("link") or "").strip(), "published": _pub(it.findtext("pubDate"))})
    return out


def collect(delay=0.5):
    """→ (항목 목록, 실패한 피드 수, 전체 피드 수). 요약문은 메모리에서만 쓰고 저장하지 않는다."""
    items, failed = [], 0
    for i, (name, url) in enumerate(FEEDS):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as res:
                items += parse(res.read(), name)
        except Exception as e:  # 피드 하나 실패로 전체를 멈추지 않는다
            failed += 1
            print(f"[outlet_rss] 실패: {name}: {e}", file=sys.stderr)
        if i < len(FEEDS) - 1:
            time.sleep(delay)
    return items, failed, len(FEEDS)
