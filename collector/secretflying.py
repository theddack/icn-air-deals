"""Secret Flying 공개 특가 중 서울 출발만 → data/secretflying.json (하루 1번).

python -m collector.secretflying

- 서울 특가 목록(SOURCE) 한 페이지만 하루 한 번(KST) 받는다. robots.txt(2026-10-19 확인)는 일반 수집을 허용하고
  Crawl-delay 1을 둔다. 공개 RSS는 꺼져 있다. 봇임을 밝힌 User-Agent를 쓴다.
- 회원 전용(잠금) 카드는 제목이 없어 건너뛴다. 공개 제목에서 출발·도착·가격·통화·왕복/편도만 뽑고,
  본문·이미지는 가져오지 않는다. 링크는 Secret Flying 게시물로 둔다.
- 가격은 게시 당시 기준이다. 실제 예약 가격·남은 좌석은 확인하지 않는다. 목록에 마지막으로 보인 뒤
  KEEP_DAYS가 지나면 뺀다.
- 실패해도 이전 파일을 그대로 두고 0으로 끝낸다 (행사 수집·배포는 계속).
"""

import html
import json
import re
import sys
import urllib.request
from datetime import timedelta
from pathlib import Path

from .status import today_kst

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "secretflying.json"
SOURCE = "https://www.secretflying.com/posts/category/seoul/"
USER_AGENT = "icn-air-deals/0.1 (+https://github.com/theddack/icn-air-deals)"
KEEP_DAYS = 14

_ARTICLE = re.compile(r'<article class="[^"]*"(.*?)</article>', re.S)
_TITLE_LINK = re.compile(r'<h3 class="entry-title">\s*<a[^>]*href="(https://www\.secretflying\.com/posts/[^"]+)"[^>]*>(.*?)</a>', re.S)
# 'XMAS & NEW YEAR: Non-stop from Seoul, South Korea to Venice, Italy for only $417 USD roundtrip'
_DEAL = re.compile(r"^(?:(?P<tag>[A-Z][A-Z0-9 &'\-]+):\s*)?(?P<nonstop>Non-stop from\s+)?(?P<origin>.+?)\s+to\s+(?P<dest>.+?)\s+"
                   r"(?:for|from)\s+only\s+(?P<sym>[$€£¥₩])(?P<price>[\d,]+(?:\.\d+)?)\s*(?P<cur>[A-Z]{3})?\s*(?P<trip>roundtrip|one-way)",
                   re.I)
_SYMBOL = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW"}


def parse_title(title):
    """공개 제목 → 노선·가격. 서울 출발이 아니거나 형식이 다르면 None."""
    m = _DEAL.match(title.strip())
    if not m or not m.group("origin").lower().startswith("seoul"):
        return None
    price = float(m.group("price").replace(",", ""))
    return {"origin": m.group("origin").strip(), "destination": m.group("dest").strip(),
            "price": int(price) if price.is_integer() else price,
            "currency": (m.group("cur") or _SYMBOL[m.group("sym")]).upper(),
            "trip": "oneway" if m.group("trip").lower() == "one-way" else "roundtrip",
            "nonstop": bool(m.group("nonstop")), "tag": (m.group("tag") or "").strip() or None}


def parse(page):
    out = []
    for body in _ARTICLE.findall(page):
        m = _TITLE_LINK.search(body)
        if not m:  # 회원 전용 카드
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        deal = parse_title(title)
        if deal:
            out.append({"title": title, "url": m.group(1), **deal})
    return out


def merge(previous, items, today):
    """이전 목록과 합친다. 같은 게시물(주소)은 처음 본 날을 유지하고, KEEP_DAYS 동안 다시 안 보이면 뺀다."""
    by_url = {d["url"]: d for d in previous}
    for it in items:
        old = by_url.get(it["url"], {})
        by_url[it["url"]] = {**it, "first_seen": old.get("first_seen", today.isoformat()), "last_seen": today.isoformat()}
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    kept = [d for d in by_url.values() if d["last_seen"] >= cutoff]
    return sorted(kept, key=lambda d: (d["first_seen"], d["url"]), reverse=True)


def fetch():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", "replace")


def main(today=None):
    today = today or today_kst()
    prev = {}
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    if prev.get("fetched_on") == today.isoformat():
        print("[secretflying] 오늘 이미 받았습니다. 건너뜁니다.")
        return 0
    try:
        items = parse(fetch())
    except Exception as e:  # 사이트 문제로 배포를 멈추지 않는다
        print(f"[secretflying] 실패: {e}", file=sys.stderr)
        return 0
    deals = merge(prev.get("deals", []), items, today)
    OUT.write_text(json.dumps({"fetched_on": today.isoformat(), "source": SOURCE, "seen_today": len(items), "deals": deals},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[secretflying] 공개 서울 출발 특가 {len(items)}건 → 보관 {len(deals)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
