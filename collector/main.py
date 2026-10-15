"""수집 실행: python -m collector.main

data/articles.json  지금까지 모은 기사 (최근 ARTICLE_KEEP_DAYS일)
data/deals.json     기사를 행사 단위로 묶은 결과 — 화면이 읽는 파일
"""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import extract
from .merge import cluster_articles
from .sources import news_rss
from .status import KST, should_keep, today_kst

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARTICLE_KEEP_DAYS = 45


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def to_article(raw, now_iso):
    """RSS 항목 → 저장용 기사. 특가 기사가 아니거나 항공사를 못 찾으면 None."""
    title = extract.clean_title(raw["raw_title"], raw.get("outlet"))
    if not extract.is_sale_article(title):
        return None
    if not extract.detect_airline(title):
        return None
    return {"title": title, "outlet": raw.get("outlet"), "url": raw["url"],
            "published": raw["published"], "first_seen": now_iso}


def enrich(article):
    """저장된 기사에 추출 결과를 붙인다. 매번 다시 계산해서 파서 수정이 지난 기사에도 반영된다."""
    title = article["title"]
    pub = date.fromisoformat(article["published"])
    start, end = extract.extract_dates(title, pub)
    name = extract.extract_event_name(title)
    return {
        **article,
        "airline": extract.detect_airline(title),
        "sale_start": start.isoformat() if start else None,
        "sale_end": end.isoformat() if end else None,
        "event_name": name,
        "event_key": extract.normalize_event_name(name),
        "discount": extract.extract_discount(title),
        "from_icn": extract.icn_flag(title),
    }


def merge_articles(existing, new, today):
    seen_url = {a["url"] for a in existing}
    seen_title = {a["title"] for a in existing}
    merged = list(existing)
    added = 0
    for a in new:
        if a["url"] in seen_url or a["title"] in seen_title:
            continue
        merged.append(a)
        seen_url.add(a["url"])
        seen_title.add(a["title"])
        added += 1
    cutoff = (today - timedelta(days=ARTICLE_KEEP_DAYS)).isoformat()
    merged = [a for a in merged if a["published"] >= cutoff]
    return merged, added


def sort_key(d):
    order = {"upcoming": 0, "live": 1, "undated": 2, "ended": 3}
    return (order[d["status"]], d["sale_start"] or d["sale_end"] or "9999", d["last_published"])


def build_deals(articles, today):
    from .status import status
    deals = []
    for d in cluster_articles([enrich(a) for a in articles]):
        if not should_keep(d, today):
            continue
        s = date.fromisoformat(d["sale_start"]) if d["sale_start"] else None
        e = date.fromisoformat(d["sale_end"]) if d["sale_end"] else None
        d["status"] = status(s, e, today)
        deals.append(d)
    return sorted(deals, key=sort_key)


def main():
    now = datetime.now(KST)
    today = today_kst()
    raw, failed, total = news_rss.collect()
    if failed == total:
        print("[main] 모든 검색어가 실패해서 데이터를 갱신하지 않습니다.", file=sys.stderr)
        return 1

    new = [a for a in (to_article(r, now.isoformat(timespec="seconds")) for r in raw) if a]
    articles, added = merge_articles(load_json(DATA / "articles.json", []), new, today)
    deals = build_deals(articles, today)

    write_json(DATA / "articles.json", articles)
    write_json(DATA / "deals.json", {
        "generated_at": now.isoformat(timespec="seconds"),
        "stats": {"queries": total, "failed_queries": failed, "rss_items": len(raw),
                  "articles": len(articles), "new_articles": added, "deals": len(deals)},
        "deals": deals,
    })
    print(f"[main] 검색어 {total}개 (실패 {failed}), RSS {len(raw)}건 → 기사 {len(articles)}건 (신규 {added}) → 행사 {len(deals)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
