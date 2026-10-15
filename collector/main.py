"""수집 실행: python -m collector.main

data/articles.json  지금까지 모은 기사 (최근 ARTICLE_KEEP_DAYS일)
data/deals.json     기사를 행사 단위로 묶은 결과 — 화면이 읽는 파일
"""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import extract
from .merge import MULTI, cluster_articles
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
    """RSS 항목 → 저장용 기사. 항공권 특가(항공사 있음)도 숙박 할인(브랜드 있음)도 아니면 None."""
    title = extract.clean_title(raw["raw_title"], raw.get("outlet"))
    if not extract.category_of(title):
        return None
    return {"title": title, "outlet": raw.get("outlet"), "url": raw["url"],
            "published": raw["published"], "first_seen": now_iso}


def enrich(article):
    """저장된 기사에 추출 결과를 붙인다. 매번 다시 계산해서 파서 수정이 지난 기사에도 반영된다."""
    title = article["title"]
    pub = date.fromisoformat(article["published"])
    start, end = extract.extract_dates(title, pub)
    t_start, t_end = extract.extract_travel(title, pub)
    name = extract.extract_event_name(title)
    category = extract.category_of(title) or "flight"
    if category == "hotel":
        owner, mentioned = extract.attribute_hotel(title)
        route, route_text, from_icn = None, None, None
    else:
        owner, mentioned = extract.attribute_airline(title)
        route, route_text = extract.route_of(title)
        from_icn = extract.icn_flag(title)
    return {
        **article,
        "category": category,
        # 여러 항공사(브랜드)가 섞여 특가의 주인을 정할 수 없으면 'multi'(미분류)
        "airline": owner or MULTI,
        "airlines_mentioned": mentioned,
        "sale_start": start.isoformat() if start else None,
        "sale_end": end.isoformat() if end else None,
        "travel_start": t_start.isoformat() if t_start else None,
        "travel_end": t_end.isoformat() if t_end else None,
        "event_name": name,
        "event_key": extract.normalize_event_name(name),
        "discount": extract.extract_discount(title),
        "from_icn": from_icn,
        "route": route,
        "route_text": route_text,
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


def baseline_key(article):
    """'신규' 판정의 기준 시각을 따로 두는 묶음. 나중에 추가한 수집 대상의 첫 수집분이 신규로 뜨지 않게 한다."""
    if article["category"] == "hotel":
        return "hotel"
    return "domestic" if article["route"] == "domestic" else "flight"


def baselines(previous, now_iso):
    """지난 deals.json의 기준 시각을 이어받고, 처음 보는 묶음은 이번 수집 시각으로 정한다."""
    out = dict(previous.get("baselines") or {})
    if "flight" not in out and previous.get("baseline_first_seen"):
        out["flight"] = previous["baseline_first_seen"]
    for key in ("flight", "domestic", "hotel"):
        out.setdefault(key, now_iso)
    return out


def main():
    now = datetime.now(KST)
    today = today_kst()
    raw, failed, total = news_rss.collect()
    if failed == total:
        print("[main] 모든 검색어가 실패해서 데이터를 갱신하지 않습니다.", file=sys.stderr)
        return 1

    now_iso = now.isoformat(timespec="seconds")
    new = [a for a in (to_article(r, now_iso) for r in raw) if a]
    articles, added = merge_articles(load_json(DATA / "articles.json", []), new, today)
    deals = build_deals(articles, today)

    base = baselines(load_json(DATA / "deals.json", {}), now_iso)

    write_json(DATA / "articles.json", articles)
    write_json(DATA / "deals.json", {
        "generated_at": now_iso,
        # 묶음(flight·domestic·hotel)별 첫 수집에 들어온 기사는 '신규'가 아니다.
        # 화면은 행사의 묶음 기준 시각 이후 처음 본 것만 신규로 표시한다.
        "baselines": base,
        "baseline_first_seen": base["flight"],
        "stats": {"queries": total, "failed_queries": failed, "rss_items": len(raw),
                  "articles": len(articles), "new_articles": added, "deals": len(deals)},
        "deals": deals,
    })
    print(f"[main] 검색어 {total}개 (실패 {failed}), RSS {len(raw)}건 → 기사 {len(articles)}건 (신규 {added}) → 행사 {len(deals)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
