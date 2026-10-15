"""같은 행사를 다룬 기사들을 1건의 행사로 묶는다.

항공사가 같은 기사끼리만 비교하고, 아래 순서로 묶는다 (앞의 기준이 강하다).
1. 행사명(따옴표 안 이름)이 같거나 한쪽이 다른 쪽을 포함한다
2. 판매 시작일 또는 마감일이 같다
3. 한 기사의 행사명이 다른 기사 제목에 들어 있다 (발행일 SIMILAR_DAYS일 이내)
4. 할인 표기(예: '최대 22%')가 같고 발행일이 SIMILAR_DAYS일 이내
5. 제목 단어가 2개 이상, 비율로 TOKEN_OVERLAP 이상 겹치고 발행일이 SIMILAR_DAYS일 이내
6. 발행일이 BURST_DAYS일 이내 (보도자료 한 건에 기사가 몰리는 패턴)

어느 단계든 두 묶음의 시작일·마감일·할인 표기·행사명 중 하나라도 서로 다르면 합치지 않는다.
알려진 한계: 같은 항공사가 2일 안에 행사명·날짜·할인율 없이 다른 행사 두 개를 내면 하나로 묶인다.
"""

import re
from collections import Counter
from datetime import date

from .airlines import BY_ID

SIMILAR_DAYS = 10
TOKEN_OVERLAP = 0.3   # 공통 단어 수 / 합친 단어 수
BURST_DAYS = 2
_STOP = {"프로모션", "할인", "특가", "항공권", "최대", "진행", "실시", "시행", "국제선", "국내선", "노선",
         "이벤트", "대상", "판매", "오픈", "시작", "혜택", "항공", "여행"}


_EVENT_WORD = re.compile(r"특가|프로모션|이벤트|마켓|세일|SALE|페스타|할인|데이|위크|얼리버드|타임", re.I)


def _is_event_like(name):
    return bool(name and _EVENT_WORD.search(name))


def _tokens(title, airline_id):
    t = title
    for alias in BY_ID[airline_id]["aliases"]:
        t = t.replace(alias, " ")
    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", t)
    return {w for w in words if w not in _STOP and not re.fullmatch(r"\d+", w)}


class _Group:
    def __init__(self, a):
        self.articles = [a]
        self.starts = {a["sale_start"]} - {None}
        self.ends = {a["sale_end"]} - {None}
        # '타이밍' 같은 따옴표 속 구호는 행사명이 아니므로 충돌 판단에 쓰지 않는다
        self.names = {a.get("event_key")} - {None} if _is_event_like(a.get("event_name")) else set()
        self.discounts = {a.get("discount")} - {None}

    def compatible(self, other):
        for mine, theirs in ((self.starts, other.starts), (self.ends, other.ends),
                             (self.discounts, other.discounts)):
            if mine and theirs and not (mine & theirs):
                return False
        if self.names and other.names and not any(
                x == y or x in y or y in x for x in self.names for y in other.names):
            return False
        return True

    def absorb(self, other):
        self.articles += other.articles
        self.starts |= other.starts
        self.ends |= other.ends
        self.names |= other.names
        self.discounts |= other.discounts


def _days_apart(a, b):
    return abs((date.fromisoformat(a["published"]) - date.fromisoformat(b["published"])).days)


def _same_name(a, b):
    x, y = a.get("event_key"), b.get("event_key")
    return bool(x and y and (x == y or (min(len(x), len(y)) >= 2 and (x in y or y in x))))


def _same_date(a, b):
    return bool((a["sale_start"] and a["sale_start"] == b["sale_start"])
                or (a["sale_end"] and a["sale_end"] == b["sale_end"]))


def _same_discount(a, b):
    return bool(a.get("discount") and a["discount"] == b.get("discount") and _days_apart(a, b) <= SIMILAR_DAYS)


def _name_in_title(a, b):
    """한 기사의 행사명이 다른 기사 제목에 따옴표 없이 들어 있다."""
    if _days_apart(a, b) > SIMILAR_DAYS:
        return False
    for x, y in ((a, b), (b, a)):
        key = x.get("event_key")
        if key and len(key) >= 3 and key in y["_flat"]:
            return True
    return False


def _similar_title(a, b):
    if _days_apart(a, b) > SIMILAR_DAYS:
        return False
    shared = a["_tokens"] & b["_tokens"]
    union = a["_tokens"] | b["_tokens"]
    return len(shared) >= 2 and len(shared) / len(union) >= TOKEN_OVERLAP


RULES = [_same_name, _same_date, _name_in_title, _same_discount, _similar_title]


def _unique_groups(items, owner):
    seen, out = set(), []
    for a in items:
        g = owner[id(a)]
        if id(g) not in seen:
            seen.add(id(g))
            out.append(g)
    return out


def _merge_bursts(groups):
    """6단계: 작은 묶음부터, BURST_DAYS 이내에 기사가 있는 다른 묶음 중
    제목 단어가 가장 많이 겹치는 곳으로 합친다. 보도자료 하나에 기사가 몰리는 경우를 처리한다."""
    def close(g, h):
        return any(_days_apart(a, b) <= BURST_DAYS for a in g.articles for b in h.articles)

    def tokens(g):
        return set().union(*(a["_tokens"] for a in g.articles))

    groups = list(groups)
    for g in sorted(groups, key=lambda g: len(g.articles)):
        if g not in groups:
            continue
        cands = [h for h in groups if h is not g and close(g, h) and g.compatible(h)]
        if not cands:
            continue
        tg = tokens(g)
        best = max(cands, key=lambda h: (len(tg & tokens(h)), len(h.articles)))
        best.absorb(g)
        groups.remove(g)
    return groups


def _cluster_one_airline(items):
    owner = {id(a): _Group(a) for a in items}
    for rule in RULES:
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                ga, gb = owner[id(a)], owner[id(b)]
                if ga is gb or not rule(a, b) or not ga.compatible(gb):
                    continue
                ga.absorb(gb)
                for art in gb.articles:
                    owner[id(art)] = ga
    return _merge_bursts(_unique_groups(items, owner))


def cluster_articles(articles):
    """articles: extract 결과가 붙은 기사 dict 목록 → 행사 dict 목록."""
    by_airline = {}
    for a in articles:
        by_airline.setdefault(a["airline"], []).append({
            **a,
            "_tokens": _tokens(a["title"], a["airline"]),
            "_flat": re.sub(r"[\s\W_]+", "", a["title"]).lower(),
        })
    deals = []
    for airline_id, items in by_airline.items():
        items.sort(key=lambda a: a["published"])
        for g in _cluster_one_airline(items):
            deals.append(_to_deal(airline_id, g.articles))
    return deals


def _mode(values):
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else None


def _to_deal(airline_id, arts):
    arts = sorted(arts, key=lambda a: a["published"])
    airline = BY_ID[airline_id]
    start = _mode(a["sale_start"] for a in arts)
    end = _mode(a["sale_end"] for a in arts)
    icn = [a["from_icn"] for a in arts]
    from_icn = "yes" if "yes" in icn else ("no" if all(x == "no" for x in icn) else "unknown")
    key_part = _mode(a.get("event_key") for a in arts) or start or end or arts[0]["published"]
    return {
        "id": f"{airline_id}-{key_part}",
        "airline_id": airline_id,
        "airline": airline["name"],
        "kind": airline["kind"],
        "event_name": _mode(a.get("event_name") for a in arts if _is_event_like(a.get("event_name"))),
        "headline": arts[-1]["title"],
        "sale_start": start,
        "sale_end": end,
        "date_source": "title" if (start or end) else "none",
        "from_icn": from_icn,
        "discount": _mode(a.get("discount") for a in arts),
        "first_published": arts[0]["published"],
        "last_published": arts[-1]["published"],
        "articles": [
            {"title": a["title"], "outlet": a.get("outlet"), "url": a["url"], "published": a["published"]}
            for a in reversed(arts)
        ],
    }
