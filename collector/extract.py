"""기사 제목에서 항공사·판매 기간·할인 정보·인천 출발 여부를 뽑는다.

날짜는 기사 발행일(KST)을 기준으로 해석한다. 제목에 연도가 거의 안 나오므로
월/연도는 발행일에서 추정한다.
"""

import re
from datetime import date, timedelta

from .airlines import AIRLINES
from .hotels import BY_ID as HOTEL_BY_ID, HOTELS

# ---------------------------------------------------------------- 제목 정리

def clean_title(title, source=None):
    """'제목 - 언론사' 형식의 꼬리를 뗀다."""
    title = title.strip()
    if source and title.endswith(" - " + source):
        return title[: -len(" - " + source)].strip()
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title


# ---------------------------------------------------------------- 항공사

def _alias_pattern(alias):
    if re.fullmatch(r"[A-Za-z]+", alias):
        return re.compile(r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])")
    return re.compile(re.escape(alias))


def _alias_table(entries):
    return sorted(
        ((a["id"], alias, _alias_pattern(alias)) for a in entries for alias in a["aliases"]),
        key=lambda x: -len(x[1]),
    )


_ALIASES = _alias_table(AIRLINES)
_HOTEL_ALIASES = _alias_table(HOTELS)


def airlines_in(text, table=_ALIASES):
    """text에 나오는 항공사 id를 처음 나온 순서대로. 긴 표기부터 찾고 찾은 자리는 지운다."""
    found = []  # (pos, id)
    masked = text
    for airline_id, alias, pat in table:
        for m in pat.finditer(masked):
            found.append((m.start(), airline_id))
            masked = masked[: m.start()] + "\0" * len(alias) + masked[m.end():]
    out = []
    for _, airline_id in sorted(found):
        if airline_id not in out:
            out.append(airline_id)
    return out


# 제목을 절로 나누는 구분자. '·'는 "이스타·에어프레미아"처럼 주어를 나열할 때 쓰여서 나누지 않는다.
_SEGMENT_SPLIT = re.compile(r"…|\.{2,}|⋯|→|,|\||\[|\]|\s-\s")


def attribute_airline(title):
    """특가가 누구 것인지 정한다 → (airline_id 또는 None, 제목에 나온 항공사 목록).

    특가 표현이 있는 절마다 그 절의 항공사(없으면 가장 가까운 앞 절, 그것도 없으면 뒤 절)를 모은다.
    모은 항공사가 하나일 때만 확정하고, 둘 이상이면 None(미분류)이다.
    """
    mentioned = airlines_in(title)
    if len(mentioned) <= 1:
        return (mentioned[0] if mentioned else None), mentioned

    segs = [s for s in _SEGMENT_SPLIT.split(title) if s.strip()]
    seg_airlines = [airlines_in(s) for s in segs]
    owners = []
    for i, seg in enumerate(segs):
        if not _SALE_CLAUSE.search(seg):
            continue
        if seg_airlines[i]:
            owners += seg_airlines[i]
            continue
        before = [seg_airlines[j] for j in range(i - 1, -1, -1) if seg_airlines[j]]
        after = [seg_airlines[j] for j in range(i + 1, len(segs)) if seg_airlines[j]]
        if before:
            owners += before[0]
        elif after:
            owners += after[0]
    owners = list(dict.fromkeys(owners))
    return (owners[0] if len(owners) == 1 else None), mentioned


def detect_airline(title):
    """특가의 주인인 항공사 id. 여러 항공사가 섞여 판단할 수 없으면 None."""
    return attribute_airline(title)[0]


# ---------------------------------------------------------------- 특가 기사 판별

# 이 말이 있으면 그 자체로 항공권 특가 기사
_SALE_STRONG = re.compile(r"특가|얼리버드|세일|SALE|Sale|반값")
# 이 말은 기내식·호텔·카드 할인에도 쓰여서 항공권 맥락이 같이 있어야 한다
_SALE_WEAK = re.compile(r"할인|프로모션|이벤트")
# 절 단위로 특가의 주인을 찾을 때 쓰는 표현 (쿠폰·%도 포함)
_SALE_CLAUSE = re.compile(r"특가|얼리버드|세일|SALE|Sale|반값|할인|프로모션|이벤트|쿠폰|\d{1,3}\s?%")
_TICKET = re.compile(r"항공권|운임|노선|국제선|국내선|편도|왕복|항공편|좌석|\d{1,3}\s?%|\d\s?원부터|[가-힣]{2,}행\b|~[가-힣]{2,}")
_NOISE = re.compile(r"퀴즈|정답|주가|증권|목표가|실적|영업이익|영업손실|채용|사고|추락|비상착륙|국정감사|과징금"
                    r"|마일리지 적립|마일리지 프로모션|기내식|면세점|팝업스토어")


def is_sale_article(title):
    if _NOISE.search(title):
        return False
    if _SALE_STRONG.search(title):
        return True
    return bool(_SALE_WEAK.search(title) and _TICKET.search(title))


# ---------------------------------------------------------------- 날짜

_DATE = re.compile(
    r"(?P<rel>오늘|내일|모레)"
    r"|(?:(?P<nm>다음\s?달|내달)\s*)?(?:(?P<mo>\d{1,2})\s?월\s*)?(?P<d>\d{1,2})\s?일(?!\s?(?:간|째|동안))"
)
_START_SUFFIX = re.compile(r"\s*(?:부터|시작|오픈|개막|개시|열린다|진행)")
_END_SUFFIX = re.compile(r"\s*(?:까지|마감|종료)")
_RANGE_BETWEEN = re.compile(r"\s*(?:부터\s*[~∼\-–]?|[~∼\-–])\s*")
# 날짜 뒤에 이 말이 붙으면 판매 기간이 아니라 탑승·취항 날짜다.
_TRAVEL_AFTER = re.compile(r"^.{0,8}?(?:탑승|출발편|출발|여행|운항|취항|직항|투숙|체크인)")
_DURATION = re.compile(r"(\d{1,2})\s?일\s?(?:간|동안)|(이틀|사흘|나흘|닷새|엿새|이레|일주일)\s?(?:간|동안)?")
_KOREAN_DAYS = {"이틀": 2, "사흘": 3, "나흘": 4, "닷새": 5, "엿새": 6, "이레": 7, "일주일": 7}
# 숫자 없는 '~13일'처럼 앞이 '13~16일'인 경우: 앞 숫자에 '일'이 없다.
_SHORT_RANGE = re.compile(r"(?:(\d{1,2})\s?월\s*)?(\d{1,2})\s?[~∼\-–]\s?(?:(\d{1,2})\s?월\s*)?(\d{1,2})\s?일")


def _add_months(year, month, n):
    month += n
    while month > 12:
        month -= 12
        year += 1
    return year, month


def _resolve(m, pub, base=None):
    """정규식 매치 하나를 date로. base는 범위의 앞쪽 날짜(뒤쪽 날짜 해석용)."""
    if m.group("rel"):
        return pub + timedelta(days={"오늘": 0, "내일": 1, "모레": 2}[m.group("rel")])
    day = int(m.group("d"))
    return _resolve_parts(m.group("mo"), day, pub, base, next_month=bool(m.group("nm")))


def _resolve_parts(mo, day, pub, base=None, next_month=False):
    try:
        if base is not None and not mo:
            y, mth = base.year, base.month
            d = date(y, mth, day)
            if d < base:
                y, mth = _add_months(y, mth, 1)
                d = date(y, mth, day)
            return d
        if next_month:
            y, mth = _add_months(pub.year, pub.month, 1)
            return date(y, mth, day)
        if mo:
            mth = int(mo)
            d = date(pub.year, mth, day)
            if d < pub - timedelta(days=60):
                d = date(pub.year + 1, mth, day)
            return d
        d = date(pub.year, pub.month, day)
        if day < pub.day - 7:
            y, mth = _add_months(pub.year, pub.month, 1)
            d = date(y, mth, day)
        return d
    except ValueError:
        return None


def extract_dates(title, pub):
    """(sale_start, sale_end) — 못 뽑은 쪽은 None."""
    start = end = None

    sm = _SHORT_RANGE.search(title)
    if sm and not _TRAVEL_AFTER.match(title[sm.end():]):
        start = _resolve_parts(sm.group(1), int(sm.group(2)), pub)
        if start:
            mo2 = sm.group(3) or None
            end = _resolve_parts(mo2, int(sm.group(4)), pub, base=None if mo2 else start)

    matches = list(_DATE.finditer(title))
    i = 0
    while i < len(matches):
        m = matches[i]
        rest = title[m.end():]
        nxt = matches[i + 1] if i + 1 < len(matches) else None

        # 범위: A ~ B, A부터 B까지
        between = title[m.end(): nxt.start()] if nxt else None
        if between is not None and _RANGE_BETWEEN.fullmatch(between):
            a = _resolve(m, pub)
            b = _resolve(nxt, pub, base=a) if a else None
            after_b = re.sub(r"^\s*까지", "", title[nxt.end():])
            if a and b and not _TRAVEL_AFTER.match(after_b):
                start = start or a
                end = end or b
            i += 2
            continue

        s = _START_SUFFIX.match(rest)
        e = _END_SUFFIX.match(rest)
        if s and not _TRAVEL_AFTER.match(rest[s.end():]):
            start = start or _resolve(m, pub)
        elif e and not _TRAVEL_AFTER.match(rest[e.end():]):
            end = end or _resolve(m, pub)
        i += 1

    if start and not end:
        dm = _DURATION.search(title)
        if dm:
            n = int(dm.group(1)) if dm.group(1) else _KOREAN_DAYS[dm.group(2)]
            if 1 <= n <= 60:
                end = start + timedelta(days=n - 1)

    if start and end and end < start:
        end = None
    return start, end


# ---------------------------------------------------------------- 할인 정보

def extract_discount(title):
    m = re.search(r"최대\s?(\d{1,3})\s?%", title)
    if m:
        return f"최대 {m.group(1)}%"
    m = re.search(r"(\d{1,3})\s?%\s?(?:할인|특가)", title)
    if m:
        return f"{m.group(1)}% 할인"
    m = re.search(r"(\d[\d,]*(?:만\s?\d[\d,]*)?\s?만?\s?원)\s?(?:부터|~)", title)
    if m:
        return re.sub(r"\s", "", m.group(1)) + "부터"
    # 숙박 쿠폰처럼 금액으로 깎아 주는 행사: '최대 7만원 할인', '최대 ‘3만 원’ 선착순 할인'
    m = re.search(r"최대\s?['‘]?(\d[\d,]*\s?만?\s?원)['’]?[^%]{0,8}?할인", title)
    if m:
        return "최대 " + re.sub(r"\s", "", m.group(1)) + " 할인"
    return None


# ---------------------------------------------------------------- 탑승 기간

_TRAVEL_WORD = r"(?:탑승|출발|여행|투숙|체크인)"
_TRAVEL_END = re.compile(r"(?:(\d{1,2})\s?월\s*)?(\d{1,2})\s?일\s?까지\s?" + _TRAVEL_WORD)
_TRAVEL_MONTHS = re.compile(r"(내년\s?)?(\d{1,2})\s?[~∼\-–]\s?(\d{1,2})\s?월(?=\s?(?:" + _TRAVEL_WORD[3:-1] + r"|항공권|국제선|노선))")
_TRAVEL_NEXT_YEAR_MONTHS = re.compile(r"내년\s?(\d{1,2})\s?[~∼\-–]\s?(\d{1,2})\s?월")
_TRAVEL_QUARTER = re.compile(r"(내년|올해)\s?(\d)\s?분기")
_TRAVEL_MONTH = re.compile(r"(내년\s?)?(\d{1,2})\s?월\s?" + _TRAVEL_WORD)


def _month_year(month, pub, next_year=False):
    if next_year:
        return pub.year + 1
    return pub.year + 1 if month < pub.month - 1 else pub.year


def _month_end(year, month):
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def extract_travel(title, pub):
    """(travel_start, travel_end) — 제목에 탑승·출발 기간이 있을 때만. 없으면 (None, None)."""
    try:
        m = _TRAVEL_END.search(title)
        if m:
            mo = int(m.group(1)) if m.group(1) else pub.month
            y = _month_year(mo, pub)
            return None, date(y, mo, int(m.group(2)))
        m = _TRAVEL_MONTHS.search(title) or _TRAVEL_NEXT_YEAR_MONTHS.search(title)
        if m:
            nxt = m.re is _TRAVEL_NEXT_YEAR_MONTHS or bool(m.group(1))
            a, b = (int(m.group(1)), int(m.group(2))) if m.re is _TRAVEL_NEXT_YEAR_MONTHS else (int(m.group(2)), int(m.group(3)))
            if 1 <= a <= 12 and 1 <= b <= 12:
                ya = _month_year(a, pub, nxt)
                yb = ya + (b < a)
                return date(ya, a, 1), _month_end(yb, b)
        m = _TRAVEL_QUARTER.search(title)
        if m and 1 <= int(m.group(2)) <= 4:
            y = pub.year + (m.group(1) == "내년")
            q = int(m.group(2))
            return date(y, 3 * q - 2, 1), _month_end(y, 3 * q)
        m = _TRAVEL_MONTH.search(title)
        if m and 1 <= int(m.group(2)) <= 12:
            mo = int(m.group(2))
            y = _month_year(mo, pub, bool(m.group(1)))
            return date(y, mo, 1), _month_end(y, mo)
    except ValueError:
        pass
    return None, None


# ---------------------------------------------------------------- 인천 출발

_OTHER_ORIGIN = re.compile(r"(김포|김해|부산|대구|청주|무안|양양|광주|제주)\s?(?:출발|발\b|[-~–])")
# 단순 언급("인천공항 라운지")이 아니라 인천이 출발지라는 근거
_ICN_ORIGIN = re.compile(r"인천\s?(?:[~∼\-–→]|발(?![가-힣])|출발|공항\s?출발)|ICN\s?[~∼\-–→]")


def icn_flag(title):
    """'yes' | 'no' | 'unknown' — yes는 노선·출발 표현이 있을 때만."""
    if _ICN_ORIGIN.search(title):
        return "yes"
    if _OTHER_ORIGIN.search(title):
        return "no"
    if "국내선" in title and "국제선" not in title:
        return "no"
    return "unknown"


# ---------------------------------------------------------------- 행사명

_QUOTED = re.compile(r"[‘'“\"`「『]([^’'”\"`」』]{2,24})[’'”\"`」』]")


def extract_event_name(title):
    for m in _QUOTED.finditer(title):
        name = m.group(1).strip()
        if re.search(r"%|원|\d{1,2}\s?일", name):
            continue
        return name
    return None


def normalize_event_name(name):
    if not name:
        return None
    n = re.sub(r"\(.*?\)", "", name)
    n = re.sub(r"\d{2,4}\s?년?|상반기|하반기|연중\s?최대", "", n)
    n = re.sub(r"[\s\W_]+", "", n).lower()
    return n or None


# ---------------------------------------------------------------- 국내선

# 국내선 공항 도시. '제주항공'·'에어부산' 같은 항공사 이름은 지운 뒤에 찾는다.
_DOMESTIC_CITY = r"(?:김포|제주|김해|부산|청주|대구|광주|여수|울산|사천|포항|군산|원주|양양|무안|서울)"
_DOMESTIC_PAIR = re.compile(rf"({_DOMESTIC_CITY})\s?[~∼\-–→]\s?({_DOMESTIC_CITY})")
_DOMESTIC_JEJU = re.compile(r"제주\s?(?:행|노선|항공권|왕복|편도)")


def route_of(title):
    """(노선 구분, 노선 표기) — 구분은 'domestic' | 'international' | None, 표기는 '김포~제주'처럼 제목에 있을 때만."""
    masked = title
    for _, alias, pat in _ALIASES:
        masked = pat.sub(" ", masked)
    m = _DOMESTIC_PAIR.search(masked)
    if m and m.group(1) != m.group(2) and "국제선" not in masked:
        return "domestic", f"{m.group(1)}~{m.group(2)}"
    if "국제선" in masked:
        return "international", None
    if "국내선" in masked or _DOMESTIC_JEJU.search(masked):
        return "domestic", None
    if _ICN_ORIGIN.search(title):
        return "international", None
    return None, None


# ---------------------------------------------------------------- 호텔·숙박

def hotels_in(text):
    return airlines_in(text, _HOTEL_ALIASES)


# 숙박 맥락. 브랜드 이름에 '호텔'이 들어 있으면 그것으로도 충족한다
_HOTEL_CONTEXT = re.compile(r"호텔|리조트|숙박|숙소|객실|호캉스|스테이|펜션|투숙|체크인|풀빌라|레지던스|스위트")
_HOTEL_SALE = re.compile(r"특가|할인|세일|SALE|Sale|쿠폰|반값|\d{1,3}\s?%|얼리버드|타임딜|페스타|슈퍼위크|최저가")
# 2026-10-15 표본(브랜드 26곳 검색 결과 691건)에서 숙박 할인이 아닌데 걸린 유형
_HOTEL_NOISE = re.compile(r"주가|증권|실적|영업이익|매출|채용|인수|매각|상장|IPO|소송|과징금|노조|사고|화재|수상|어워드|어워즈"
                          r"|선정|기부|협약|MOU|ESG|임명|인사|대표이사|투자|적자|흑자|순이익"
                          r"|뷔페|디저트|케이크|침구|매트리스|골프|카지노|eSIM")


def is_hotel_sale(title):
    return bool(hotels_in(title) and _HOTEL_CONTEXT.search(title) and _HOTEL_SALE.search(title)
                and not _HOTEL_NOISE.search(title))


def attribute_hotel(title):
    """→ (브랜드 id 또는 None, 제목에 나온 브랜드 목록).

    숙박세일 페스타 같은 정부 행사가 나오면 참여 플랫폼이 여럿이어도 그 행사로 본다.
    그 밖에 브랜드가 둘 이상이면 None(미분류)."""
    mentioned = hotels_in(title)
    campaigns = [h for h in mentioned if HOTEL_BY_ID[h]["kind"] == "campaign"]
    if campaigns:
        return campaigns[0], mentioned
    return (mentioned[0] if len(mentioned) == 1 else None), mentioned


def category_of(title):
    """'flight' | 'hotel' | None(수집 대상 아님). 항공사 특가 판정이 우선이다."""
    if is_sale_article(title) and airlines_in(title):
        return "flight"
    if is_hotel_sale(title):
        return "hotel"
    return None
