"""같은 행사를 다룬 기사들을 1건의 행사로 묶는다.

항공사가 같은 기사끼리만 비교하고, 아래 순서로 묶는다 (앞의 기준이 강하다).
1. 행사명(따옴표 안 이름)이 같거나 한쪽이 다른 쪽을 포함한다
2. 판매 시작일 또는 마감일이 같다
3. 한 기사의 행사명이 다른 기사 제목에 들어 있다 (발행일 SIMILAR_DAYS일 이내)
4. 할인 표기(예: '최대 22%')가 같고 발행일이 SIMILAR_DAYS일 이내
5. 제목 단어가 2개 이상, 비율로 TOKEN_OVERLAP 이상 겹치고 발행일이 SIMILAR_DAYS일 이내
6. 발행일이 BURST_DAYS일 이내 (보도자료 한 건에 기사가 몰리는 패턴). 호텔은 흔한 숙박 용어 말고 겹치는 단어도 있어야 한다

어느 단계든 두 묶음의 시작일·마감일·할인 표기·행사명·노선 구분(국내선/국제선) 중 하나라도 서로 다르면 합치지 않는다.
호텔·숙박 기사도 같은 규칙으로 묶는다(브랜드 id는 'h-'로 시작해 항공사와 겹치지 않는다).
알려진 한계: 같은 항공사가 2일 안에 행사명·날짜·할인율 없이 다른 행사 두 개를 내면 하나로 묶인다.
"""

import hashlib
import re
from collections import Counter
from datetime import date

from .airlines import BY_ID as AIRLINE_BY_ID
from .hotels import BY_ID as HOTEL_BY_ID

BY_ID = {**AIRLINE_BY_ID, **HOTEL_BY_ID}

MULTI = "multi"  # 여러 항공사가 섞인 미분류 기사
SIMILAR_DAYS = 10
TOKEN_OVERLAP = 0.3   # 공통 단어 수 / 합친 단어 수
BURST_DAYS = 2
_STOP = {"프로모션", "할인", "특가", "항공권", "최대", "진행", "실시", "시행", "국제선", "국내선", "노선",
         "이벤트", "대상", "판매", "오픈", "시작", "혜택", "항공", "여행",
         # 영어 호텔 기사 (시범)
         "hotel", "hotels", "sale", "off", "resort", "resorts", "stays", "stay", "rooms", "discount", "deals", "the", "and", "with", "for"}


_EVENT_WORD = re.compile(r"특가|프로모션|이벤트|마켓|세일|SALE|페스타|할인|데이|위크|얼리버드|타임", re.I)


def _is_event_like(name):
    return bool(name and _EVENT_WORD.search(name))


def _tokens(title, airline_id):
    t = title
    for alias in BY_ID[airline_id]["aliases"]:
        t = t.replace(alias, " ")
    # 같은 말의 다른 표기: '지방공항'·'지역공항'·'지역 공항'을 같은 단어로 본다
    t = re.sub(r"지방", "지역", t)
    t = re.sub(r"(\S)공항", r"\1 공항", t)
    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", t)
    return {w.lower() for w in words if w.lower() not in _STOP and not re.fullmatch(r"\d+", w)}


class _Group:
    def __init__(self, a):
        self.articles = [a]
        self.starts = {a["sale_start"]} - {None}
        self.ends = {a["sale_end"]} - {None}
        # '타이밍' 같은 따옴표 속 구호는 행사명이 아니므로 충돌 판단에 쓰지 않는다
        self.names = {a.get("event_key")} - {None} if _is_event_like(a.get("event_name")) else set()
        self.discounts = {a.get("discount")} - {None}
        self.routes = {a.get("route")} - {None}

    def compatible(self, other):
        for mine, theirs in ((self.starts, other.starts), (self.ends, other.ends),
                             (self.discounts, other.discounts), (self.routes, other.routes)):
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
        self.routes |= other.routes


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


_PARTICLE = re.compile(r"(?:에서도|에서|으로|과|와|은|는|이|가|을|를|에|의|도|로|서)$")
# 숙박 기사라면 어디에나 나오는 말. 호텔 묶기에서 '같은 행사' 근거로 쓰지 않는다
_HOTEL_GENERIC = {"숙소", "숙박", "숙박시설", "호텔", "객실", "리조트", "투숙객", "가을", "겨울", "혜택", "쿠폰", "제공", "대상"}


def _stems(tokens):
    return {_PARTICLE.sub("", w) for w in tokens} - _HOTEL_GENERIC - {""}


def _merge_bursts(groups, need_shared_word=False):
    """6단계: 작은 묶음부터, BURST_DAYS 이내에 기사가 있는 다른 묶음 중
    제목 단어가 가장 많이 겹치는 곳으로 합친다. 보도자료 하나에 기사가 몰리는 경우를 처리한다.

    need_shared_word: 호텔용. 숙박 플랫폼은 같은 날 지역별 행사를 여러 개 내므로
    (2026-10-02 여기어때 가평 할인·제주 그린키 페스타) 흔한 숙박 용어 말고 겹치는 단어가 있어야 합친다."""
    def close(g, h):
        return any(_days_apart(a, b) <= BURST_DAYS for a in g.articles for b in h.articles)

    def tokens(g):
        return set().union(*(a["_tokens"] for a in g.articles))

    def shares_word(g, h):
        return not need_shared_word or bool(_stems(tokens(g)) & _stems(tokens(h)))

    groups = list(groups)
    for g in sorted(groups, key=lambda g: len(g.articles)):
        if g not in groups:
            continue
        cands = [h for h in groups if h is not g and close(g, h) and g.compatible(h) and shares_word(g, h)]
        if not cands:
            continue
        tg = tokens(g)
        best = max(cands, key=lambda h: (len(tg & tokens(h)), len(h.articles)))
        best.absorb(g)
        groups.remove(g)
    return groups


def _cluster_one_airline(items, hotel=False):
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
    return _merge_bursts(_unique_groups(items, owner), need_shared_word=hotel)


def cluster_articles(articles):
    """articles: extract 결과가 붙은 기사 dict 목록 → 행사 dict 목록.

    airline이 MULTI(여러 항공사가 섞여 특가의 주인을 못 정한 기사)면 묶지 않고 기사 1건 = 행사 1건.
    """
    by_airline = {}
    deals = []
    other = []
    for a in articles:
        # 미분류(여러 항공사·브랜드)와 '브랜드 미확인' 호텔 기사는 묶을 근거가 없어 기사 1건 = 행사 1건
        if a["airline"] == MULTI:
            deals.append(_to_deal(a["airline"], [a]))
            continue
        # 단, 브랜드 미확인이어도 따옴표 행사명이 같으면(한쪽이 다른 쪽을 포함해도) 같은 행사로 본다.
        # 2026-10-15·17 '괌 가을 페이백'과 '가을 페이백'이 따로 보였다
        if a["airline"] == "h-other":
            other.append(a)
            continue
        by_airline.setdefault(a["airline"], []).append({
            **a,
            "_tokens": _tokens(a["title"], a["airline"]),
            "_flat": re.sub(r"[\s\W_]+", "", a["title"]).lower(),
        })
    for airline_id, items in by_airline.items():
        items.sort(key=lambda a: a["published"])
        for g in _cluster_one_airline(items, hotel=airline_id.startswith("h-")):
            deals.append(_to_deal(airline_id, g.articles))
    deals += [_to_deal("h-other", g) for g in _group_by_name(other)]
    return deals


OTHER_NAME_DAYS = 14  # 브랜드 미확인 기사를 행사명으로 묶을 때 발행일 차이 한도
OTHER_NAME_MIN = 4    # 포함 관계로 볼 행사명 최소 길이 ('페이백' 같은 일반어만으로는 묶지 않는다)


def _same_name(a, b):
    if not a or not b:
        return False
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= OTHER_NAME_MIN and short in long_)


def _group_by_name(articles):
    groups = []
    for a in sorted(articles, key=lambda a: a["published"]):
        key = a.get("event_key")
        hit = next((g for g in groups if any(
            _same_name(key, b.get("event_key"))
            and abs((date.fromisoformat(a["published"]) - date.fromisoformat(b["published"])).days) <= OTHER_NAME_DAYS
            for b in g)), None)
        if hit is not None:
            hit.append(a)
        else:
            groups.append([a])
    return groups


def _mode(values):
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else None


def _evidence(arts, chosen):
    """필드별 근거 기사: 고른 값을 담은 가장 최근 기사의 제목·주소. arts는 발행일 오름차순."""
    out = {}
    for field, test in chosen.items():
        for a in reversed(arts):
            if test(a):
                # 요약문에서 채운 값이면 요약문 근거 구절과 언론사 원문 주소를 근거로 쓴다
                out[field] = a.get("_src", {}).get(field) or {"title": a["title"], "url": a["url"]}
                break
    return out


def _agencies(arts):
    from .extract import hotels_in
    seen = []
    for a in arts:
        for hid in hotels_in(a["title"]):
            h = HOTEL_BY_ID[hid]
            if h["kind"] == "platform" and h.get("official_url") and hid not in seen:
                seen.append(hid)
    return [{"name": HOTEL_BY_ID[h]["name"], "url": HOTEL_BY_ID[h]["official_url"]} for h in seen]


def _distinct(values):
    return list(dict.fromkeys(v for v in values if v))


def _to_deal(airline_id, arts):
    arts = sorted(arts, key=lambda a: (a["published"], a["url"]))
    category = arts[0].get("category", "flight")
    if airline_id == MULTI:
        names = [BY_ID[i]["name"] for i in arts[0].get("airlines_mentioned", [])]
        airline = {"name": "여러 브랜드" if category == "hotel" else "여러 항공사", "kind": "mixed"}
    else:
        airline = BY_ID[airline_id]
        names = [airline["name"]]
    start = _mode(a["sale_start"] for a in arts)
    end = _mode(a["sale_end"] for a in arts)
    icn = [a["from_icn"] for a in arts]
    if category == "hotel":
        from_icn = None
    else:
        # 인천 출발 근거가 하나라도 있으면 yes. 없고 다른 출발지(한국행 포함)가 명시된 기사가 있으면 no
        # (같은 행사 기사 대부분은 출발지를 말하지 않는다 — 2026-10-18 '우리 동네 할인' 4건 중 1건만 '광주 출발')
        from_icn = "yes" if "yes" in icn else ("no" if "no" in icn else "unknown")
    routes = {a.get("route") for a in arts} - {None}
    route = routes.pop() if len(routes) == 1 else None  # compatible()이 서로 다른 구분을 막는다
    section = "hotel" if category == "hotel" else ("domestic" if route == "domestic" else "flight")
    scopes = {a.get("scope") for a in arts} - {None}
    scope = ("overseas" if "overseas" in scopes else "domestic" if scopes else None) if category == "hotel" else None
    lang = "en" if all(a.get("lang") == "en" for a in arts) else "ko"

    # 탑승(투숙) 기간은 묶기 충돌 검사 대상이 아니라 기사끼리 다를 수 있다. 다르면 고르지 않고 '출처 간 불일치'로 둔다.
    conflicts = []
    t_start, t_end = _mode(a.get("travel_start") for a in arts), _mode(a.get("travel_end") for a in arts)
    travel_pairs = _distinct((a.get("travel_start"), a.get("travel_end")) for a in arts
                             if a.get("travel_start") or a.get("travel_end"))
    if len(travel_pairs) > 1:
        conflicts.append("travel")
        t_start = t_end = None
    # 한 행사가 여러 노선을 다루는 일은 흔하다(예: 인천~구마모토·부산~마닐라). 불일치가 아니라 목록으로 둔다.
    routes = _distinct((a.get("origin"), a.get("destination")) for a in arts if a.get("origin") or a.get("destination"))
    regions = Counter(r for a in arts for r in a.get("regions", []))
    conditions = Counter(c for a in arts for c in a.get("conditions", []))
    start_, end_ = start, end
    discount = _mode(a.get("discount") for a in arts)
    seen = sorted(a["first_seen"] for a in arts)
    return {
        "id": f"{airline_id}-{hashlib.sha1(arts[0]['url'].encode()).hexdigest()[:10]}",
        "airline_id": airline_id,
        "airline": airline["name"],
        "airlines_mentioned": names,
        "kind": airline["kind"],
        "category": category,
        # 화면의 탭이자 '신규' 기준 시각의 묶음: flight(인천 출발 항공권) | domestic(국내선) | hotel(호텔·숙박)
        "section": section,
        "route": route,
        "route_text": _mode(a.get("route_text") for a in arts),
        # 호텔 지역(국내/해외)과 시범 여부. 해외 호텔·영어 기사는 2026-10-15 시작한 시범 수집이다
        "scope": scope,
        "lang": lang,
        "trial": category == "hotel" and (scope == "overseas" or lang == "en"),
        # 화면의 '신규' 판정에 쓸 기준 시각 묶음 (deals.json baselines의 키)
        "baseline": "hotel_trial" if category == "hotel" and (scope == "overseas" or lang == "en") else section,
        "official_url": airline.get("official_url"),
        "iata": airline.get("iata", []),
        # 항공권 기사 제목에 나온 예약 플랫폼·여행사 (할인을 그곳에서 판다는 근거가 기사에 있을 때만 화면에 링크)
        "agencies": _agencies(arts) if category == "flight" else [],
        "event_name": _mode(a.get("event_name") for a in arts if _is_event_like(a.get("event_name"))),
        "headline": arts[-1]["title"],
        "sale_start": start,
        "sale_end": end,
        "travel_start": t_start,
        "travel_end": t_end,
        "routes": [{"origin": o, "destination": d} for o, d in routes],
        "regions": [r for r, _ in regions.most_common(4)],
        "conditions": [c for c, _ in conditions.most_common()],
        "conflicts": conflicts,
        "evidence": _evidence(arts, {
            "sale": lambda a: (a["sale_start"] or a["sale_end"]) and a["sale_start"] in (start_, None) and a["sale_end"] in (end_, None),
            "travel": lambda a: bool(t_start or t_end) and (a.get("travel_start"), a.get("travel_end")) == (t_start, t_end),
            "discount": lambda a: bool(discount) and a.get("discount") == discount,
            "route": lambda a: bool(a.get("origin") or a.get("destination") or a.get("route_text")),
        }),
        "date_source": "title" if (start or end) else "none",
        "from_icn": from_icn,
        "discount": discount,
        # 지금은 모든 행사가 뉴스 기사 기반이다. 공식 페이지에서 확인한 행사가 생기면 'official'.
        "verification": "news",
        "first_published": arts[0]["published"],
        "last_published": arts[-1]["published"],
        "first_seen": seen[0],
        "last_seen": seen[-1],
        "articles": [
            {"title": a["title"], "outlet": a.get("outlet"), "url": a["url"], "published": a["published"]}
            for a in reversed(arts)
        ],
    }
