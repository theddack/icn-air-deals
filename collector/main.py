"""수집 실행: python -m collector.main

data/articles.json  지금까지 모은 기사 (최근 ARTICLE_KEEP_DAYS일)
data/deals.json     기사를 행사 단위로 묶은 결과 — 화면이 읽는 파일
"""

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import extract
from .merge import MULTI, cluster_articles
from .sources import news_rss, outlet_rss
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
    lang = raw.get("lang", "ko")
    if not extract.category_of(title, lang):
        return None
    a = {"title": title, "outlet": raw.get("outlet"), "url": raw["url"],
         "published": raw["published"], "first_seen": now_iso}
    if lang != "ko":
        a["lang"] = lang
    return a


def norm_title(t):
    return re.sub(r"[\s\W_]+", "", t or "").lower()


def summary_facts(item):
    """언론사 RSS 항목 → 저장용 사실값. 요약문 자체는 저장하지 않는다."""
    if not item.get("published"):
        return None
    facts, evidence = extract.facts_from_summary(item["summary"], date.fromisoformat(item["published"]))
    if not facts:
        return None
    return {"url": item["url"], "outlet": item["outlet"],
            "fields": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in facts.items()},
            "evidence": evidence}


def attach_outlet_items(articles, items, now_iso):
    """언론사 RSS 항목을 기사에 붙인다.
    - 제목이 같은(공백·문장부호 무시) 기존 기사에는 요약문 사실값을 붙인다 (이미 있으면 그대로 둔다)
    - 어느 기사와도 안 맞고 행사 기사이면 새 기사로 더한다 (주소는 언론사 원문)
    → (새 기사 목록, 사실값을 붙인 기존 기사 수)"""
    by_norm = {norm_title(a["title"]): a for a in articles}
    new, enriched = [], 0
    for it in items:
        key = norm_title(it["title"])
        if len(key) < 8:
            continue
        target = by_norm.get(key) or next(
            (a for k, a in by_norm.items() if len(k) >= 12 and (k in key or key in k)), None)
        facts = summary_facts(it)
        if target is not None:
            if facts and not target.get("summary_facts"):
                target["summary_facts"] = facts
                enriched += 1
            continue
        if not it.get("published") or not extract.category_of(it["title"]):
            continue
        a = {"title": it["title"], "outlet": it["outlet"], "url": it["url"], "published": it["published"],
             "first_seen": now_iso, "source": "outlet_rss"}
        if facts:
            a["summary_facts"] = facts
        new.append(a)
        by_norm[key] = a
    return new, enriched


def enrich(article):
    """저장된 기사에 추출 결과를 붙인다. 매번 다시 계산해서 파서 수정이 지난 기사에도 반영된다."""
    title = article["title"]
    pub = date.fromisoformat(article["published"])
    if article.get("lang") == "en":
        return _enrich_en(article, title, pub)
    start, end = extract.extract_dates(title, pub)
    t_start, t_end = extract.extract_travel(title, pub)
    name = extract.extract_event_name(title)
    category = extract.category_of(title) or "flight"
    origin = destination = None
    regions, conditions, scope = [], [], None
    if category == "hotel":
        owner, mentioned = extract.attribute_hotel(title)
        route, route_text, from_icn = None, None, None
        regions, conditions = extract.hotel_regions(title), extract.hotel_conditions(title)
        scope = extract.hotel_scope(title, regions)
    else:
        owner, mentioned = extract.attribute_airline(title)
        route, route_text = extract.route_of(title)
        from_icn = extract.icn_flag(title)
        origin, destination = extract.airports(title)
    out = {
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
        "origin": origin,
        "destination": destination,
        "regions": regions,
        "conditions": conditions,
        "scope": scope,
    }
    return _fill_from_summary(out)


def _enrich_en(article, title, pub):
    """영어 기사(호텔 시범). 제목은 번역하지 않고 할인율·기간·지역만 규칙으로 뽑는다."""
    start, end = extract.extract_dates_en(title, pub)
    owner, mentioned = extract.attribute_hotel(title)
    regions = extract.regions_en(title)
    return {
        **article,
        "category": "hotel", "airline": owner or MULTI, "airlines_mentioned": mentioned,
        "sale_start": start.isoformat() if start else None, "sale_end": end.isoformat() if end else None,
        "travel_start": None, "travel_end": None, "event_name": None, "event_key": None,
        "discount": extract.extract_discount_en(title), "from_icn": None, "route": None, "route_text": None,
        "origin": None, "destination": None, "regions": regions, "conditions": [],
        # 영어 기사는 해외로 본다. 한국이 대상이라고 나오면 국내
        "scope": "domestic" if set(regions) & {"한국", "서울"} else "overseas",
    }


# 요약문 사실값은 제목에서 못 뽑은 필드만 채운다. 어느 필드를 요약문에서 채웠는지는 _src에 남겨 근거로 보여준다
_SUMMARY_GROUPS = {"sale": ("sale_start", "sale_end"), "travel": ("travel_start", "travel_end"),
                   "discount": ("discount",), "route": ("origin", "destination")}


def _fill_from_summary(a):
    sf = a.get("summary_facts")
    if not sf:
        return a
    src = {}
    for group, fields in _SUMMARY_GROUPS.items():
        if group == "route" and a.get("category") == "hotel":
            continue
        if any(a.get(f) for f in fields) or not any(sf["fields"].get(f) for f in fields):
            continue
        for f in fields:
            a[f] = sf["fields"].get(f)
        snippet = sf["evidence"].get(group, "")
        src[group] = {"title": f"{sf['outlet']} 요약문: {snippet}", "url": sf["url"]}
    if src:
        a["_src"] = src
    return a


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
        return "hotel_trial" if article.get("lang") == "en" or article.get("scope") == "overseas" else "hotel"
    return "domestic" if article["route"] == "domestic" else "flight"


def baselines(previous, now_iso):
    """지난 deals.json의 기준 시각을 이어받고, 처음 보는 묶음은 이번 수집 시각으로 정한다."""
    out = dict(previous.get("baselines") or {})
    if "flight" not in out and previous.get("baseline_first_seen"):
        out["flight"] = previous["baseline_first_seen"]
    # hotel_trial: 2026-10-15 시작한 해외 호텔·영어 기사 시범. 첫 수집분(지난 기사)이 신규로 뜨지 않게 따로 둔다
    for key in ("flight", "domestic", "hotel", "hotel_trial"):
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

    # 언론사 RSS: 실패해도 Google 뉴스 결과만으로 계속한다
    o_items, o_failed, o_total = outlet_rss.collect()
    o_new, o_enriched = attach_outlet_items(articles, o_items, now_iso)
    articles, o_added = merge_articles(articles, o_new, today)
    added += o_added
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
                  "outlet_feeds": o_total, "outlet_failed": o_failed, "outlet_items": len(o_items),
                  "outlet_new_articles": o_added, "outlet_enriched": o_enriched,
                  "articles_with_summary": sum(1 for a in articles if a.get("summary_facts")),
                  "articles": len(articles), "new_articles": added, "deals": len(deals)},
        "deals": deals,
    })
    print(f"[main] 검색어 {total}개 (실패 {failed}), RSS {len(raw)}건 → 기사 {len(articles)}건 (신규 {added}) → 행사 {len(deals)}건")
    print(f"[main] 언론사 RSS {o_total}곳 (실패 {o_failed}), 항목 {len(o_items)}건 → 새 기사 {o_added}, 요약 사실값 추가 {o_enriched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
