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


# 2026-10-15 보완: 항공권 맥락 단어 없이도 운임 할인 행사로 볼 수 있는 표현.
# '할인 프로모션', '할인이벤트', "'우리 동네 할인' 프로모션", '출발편 할인', '공항과 공동 프로모션'
_SALE_FARE = re.compile(r"할인['’\"”]?\s?(?:프로모션|이벤트|행사)|출발(?:편|시)\s?할인|공동\s?프로모션")
# 위 표현이 있어도 운임이 아닌 부가 상품·제휴 혜택이면 뺀다 (같은 날 표본에서 탈락시킨 31건의 유형)
_ANCILLARY = re.compile(r"멤버십|마일리지|수하물|기내|메뉴|선봬|비빔밥|막국수|팝업|환승|신규\s?(?:회원|가입)|쿠폰팩|무료\s?입장|렌터카|면세")


def is_sale_article(title):
    if _NOISE.search(title):
        return False
    if _SALE_STRONG.search(title):
        return True
    if _SALE_WEAK.search(title) and _TICKET.search(title):
        return True
    return bool(_SALE_FARE.search(title) and not _ANCILLARY.search(title))


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
    found = [m for m in _QUOTED.finditer(title) if not re.search(r"%|원|\d{1,2}\s?일", m.group(1))]
    # 제목 맨 앞의 따옴표는 대개 구호다 (“지방공항 출발시 할인” 트리니티항공, … '우리동네 프로모션').
    # 뒤에 다른 따옴표가 있으면 그쪽을 행사명으로 본다
    if len(found) > 1 and found[0].start() == 0:
        found = found[1:]
    return found[0].group(1).strip() if found else None


def normalize_event_name(name):
    if not name:
        return None
    n = re.sub(r"\(.*?\)", "", name)
    n = re.sub(r"\d{2,4}\s?년?|상반기|하반기|연중\s?최대", "", n)
    n = re.sub(r"[\s\W_]+", "", n).lower()
    # 같은 행사를 '우리 동네 할인'·'우리동네 프로모션'처럼 끝말만 바꿔 부른다. 끝의 일반어는 비교에서 뺀다
    n = re.sub(r"(?:프로모션|할인|이벤트|행사)+$", "", n)
    return n or None


# ---------------------------------------------------------------- 국내선

_DOMESTIC_JEJU = re.compile(r"제주\s?(?:행|노선|항공권|왕복|편도)")


def route_of(title):
    """(노선 구분, 노선 표기) — 구분은 'domestic' | 'international' | None, 표기는 '김포~제주'처럼 제목에 있을 때만.
    출발·도착이 모두 국내 공항이면 국내선이다(아래 airports 참고)."""
    masked = _mask_airlines(title)
    o, d = _airport_keys(masked)
    if o and d and _PLACES[o][2] and _PLACES[d][2] and "한국" not in (o, d) and "국제선" not in masked:
        return "domestic", f"{_PLACES[o][0]}~{_PLACES[d][0]}"
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
    if not mentioned:
        return "h-other", []  # 해외 숙박 할인인데 브랜드가 없는 기사 (is_overseas_hotel_sale)
    campaigns = [h for h in mentioned if HOTEL_BY_ID[h]["kind"] == "campaign"]
    if campaigns:
        return campaigns[0], mentioned
    return (mentioned[0] if len(mentioned) == 1 else None), mentioned


def category_of(title, lang="ko"):
    """'flight' | 'hotel' | None(수집 대상 아님). 항공사 특가 판정이 우선이다.
    영어 기사는 호텔 시범 수집만 한다."""
    if lang == "en":
        return "hotel" if is_hotel_sale_en(title) else None
    if is_sale_article(title) and airlines_in(title):
        return "flight"
    if is_hotel_sale(title) or is_overseas_hotel_sale(title):
        return "hotel"
    return None


# ---------------------------------------------------------------- 출발·도착 공항

# 제목에 나오는 지명 → (표시 이름, 공항 코드 또는 None, 국내 여부).
# 공항이 여럿인 도시(도쿄·상하이·방콕 등)와 나라·지역 이름은 코드를 붙이지 않는다.
_PLACES = {
    "인천": ("인천", "ICN", True), "김포": ("김포", "GMP", True), "김해": ("김해", "PUS", True), "부산": ("부산", "PUS", True),
    "제주": ("제주", "CJU", True), "청주": ("청주", "CJJ", True), "대구": ("대구", "TAE", True), "광주": ("광주", "KWJ", True),
    "무안": ("무안", "MWX", True), "양양": ("양양", "YNY", True), "여수": ("여수", "RSU", True), "울산": ("울산", "USN", True),
    "사천": ("사천", "HIN", True), "포항": ("포항", "KPO", True), "군산": ("군산", "KUV", True), "원주": ("원주", "WJU", True),
    "오사카": ("오사카", "KIX", False), "간사이": ("오사카", "KIX", False), "후쿠오카": ("후쿠오카", "FUK", False),
    "삿포로": ("삿포로", "CTS", False), "오키나와": ("오키나와", "OKA", False), "나고야": ("나고야", "NGO", False),
    "구마모토": ("구마모토", "KMJ", False), "마쓰야마": ("마쓰야마", "MYJ", False), "시즈오카": ("시즈오카", "FSZ", False),
    "나리타": ("도쿄 나리타", "NRT", False), "하네다": ("도쿄 하네다", "HND", False), "도쿄": ("도쿄", None, False),
    "다낭": ("다낭", "DAD", False), "나트랑": ("나트랑", "CXR", False), "냐짱": ("나트랑", "CXR", False), "하노이": ("하노이", "HAN", False),
    "호치민": ("호찌민", "SGN", False), "호찌민": ("호찌민", "SGN", False), "푸꾸옥": ("푸꾸옥", "PQC", False),
    "방콕": ("방콕", None, False), "치앙마이": ("치앙마이", "CNX", False), "푸껫": ("푸껫", "HKT", False),
    "세부": ("세부", "CEB", False), "마닐라": ("마닐라", "MNL", False), "보홀": ("보홀", "TAG", False), "클락": ("클락", "CRK", False),
    "싱가포르": ("싱가포르", "SIN", False), "쿠알라룸푸르": ("쿠알라룸푸르", "KUL", False), "코타키나발루": ("코타키나발루", "BKI", False),
    "발리": ("발리", "DPS", False), "타이베이": ("타이베이", None, False), "가오슝": ("가오슝", "KHH", False),
    "홍콩": ("홍콩", "HKG", False), "마카오": ("마카오", "MFM", False), "상하이": ("상하이", None, False), "베이징": ("베이징", None, False),
    "울란바토르": ("울란바토르", "UBN", False), "괌": ("괌", "GUM", False), "사이판": ("사이판", "SPN", False),
    "하와이": ("하와이", None, False), "호놀룰루": ("호놀룰루", "HNL", False),
    "일본": ("일본", None, False), "베트남": ("베트남", None, False), "필리핀": ("필리핀", None, False), "태국": ("태국", None, False),
    "중국": ("중국", None, False), "대만": ("대만", None, False), "미국": ("미국", None, False), "유럽": ("유럽", None, False),
    "한국": ("한국", None, True),
}
_PLACE = "(" + "|".join(sorted(_PLACES, key=len, reverse=True)) + ")"
_PAIR = re.compile(_PLACE + r"\s?(?:[~∼\-–→]|에서)\s?" + _PLACE + r"(?![가-힣]{2})")
_FROM = re.compile(_PLACE + r"\s?(?:발(?![가-힣])|출발)")
_TO = re.compile(_PLACE + r"\s?(?:행(?![가-힣])|노선|직항)")


def _place(name):
    label, code, _ = _PLACES[name]
    return f"{label}({code})" if code else label


def _mask_airlines(title):
    """'제주항공'·'에어부산'·'세부퍼시픽'의 지명은 노선이 아니므로 항공사 이름을 지운다."""
    for _, alias, pat in _ALIASES:
        title = pat.sub(" ", title)
    return title


def _airport_keys(masked):
    m = _PAIR.search(masked)
    if m and m.group(1) != m.group(2):
        return m.group(1), m.group(2)
    f, t = _FROM.search(masked), _TO.search(masked)
    return (f.group(1) if f else None), (t.group(1) if t else None)


def airports(title):
    """(출발, 도착) — 제목에 노선·출발·도착 표현이 있을 때만. 표시용 문자열('인천(ICN)')이며 없으면 None."""
    o, d = _airport_keys(_mask_airlines(title))
    return (_place(o) if o else None), (_place(d) if d else None)


# ---------------------------------------------------------------- 호텔 지역·조건

_REGIONS = ["서울", "인천", "경기", "가평", "강원", "속초", "강릉", "충남", "충북", "대전", "전북", "전남광주", "전남", "광주",
            "경북", "경남", "대구", "부산", "울산", "포항", "청도", "여수", "제주", "섬 지역", "비수도권",
            "일본", "규슈", "사가현", "후쿠오카", "오사카", "도쿄", "베트남", "태국"]
_REGION = re.compile("|".join(sorted(map(re.escape, _REGIONS), key=len, reverse=True)))
_CONDITIONS = [("쿠폰", r"쿠폰"), ("연박", r"연박|2박"), ("선착순", r"선착순"), ("회원 전용", r"회원"),
               ("앱 예약", r"앱(?:으로|에서)?"), ("포인트 적립", r"포인트")]


def hotel_regions(title):
    out = []
    # 해외 지명(_OVERSEAS, 파일 아래쪽)도 지역으로 쓴다. '해외'·'N개국' 같은 말은 지명이 아니라서 뺀다
    pat = re.compile(_REGION.pattern + "|" + "|".join(sorted(map(re.escape, [o for o in _OVERSEAS if o != "해외"]), key=len, reverse=True)))
    for m in pat.finditer(_mask_airlines(title)):
        r = m.group(0)
        if r not in out and not any(r in o for o in out):
            out.append(r)
    return out


def hotel_conditions(title):
    return [name for name, pat in _CONDITIONS if re.search(pat, title)]


# ---------------------------------------------------------------- 언론사 RSS 요약문

# 요약문은 여러 문장이다. 판매 기간 문장과 탑승 기간 문장을 나눠서 본다 (한 문장에 섞으면 탑승 날짜를 판매 기간으로 읽는다)
_SENTENCE = re.compile(r"(?<=[.다요])\s+|(?<=다\.)(?=\S)")
_TRAVEL_SENT = re.compile(r"(?:탑승|여행|투숙|출발|체크인)\s?(?:기간|일정|가능\s?기간)")
_SALE_SENT = re.compile(r"판매|예매|예약|구매|진행|프로모션|특가|할인|이벤트|행사")
EVIDENCE_MAX = 60  # 근거 구절은 이 길이까지만 저장한다 (요약문 전체를 공개 저장소에 두지 않는다)


def _snippet(sentence, needle=None):
    s = sentence.strip()
    if len(s) <= EVIDENCE_MAX:
        return s
    i = s.find(needle) if needle else -1
    start = max(0, min(i - 10, len(s) - EVIDENCE_MAX)) if i >= 0 else 0
    return ("…" if start else "") + s[start:start + EVIDENCE_MAX] + "…"


def _range_in(sentence, pub):
    """문장 안의 'A부터 B까지' 두 날짜 → (A, B). 하나뿐이면 (None, B) 또는 (A, None)."""
    ms = list(_DATE.finditer(sentence))
    if not ms:
        return None, None
    a = _resolve(ms[0], pub)
    if len(ms) >= 2:
        b = _resolve(ms[1], pub, base=a) if a else None
        if a and b and b >= a:
            return a, b
    rest = sentence[ms[0].end():]
    if _END_SUFFIX.match(rest):
        return None, a
    return a, None


def facts_from_summary(text, pub):
    """요약문 → {필드: 값}, {필드: 근거 구절}. 확인한 값만 넣고 없으면 비운다."""
    facts, evidence = {}, {}
    sentences = [s for s in _SENTENCE.split(text or "") if s.strip()]
    for s in sentences:
        if _TRAVEL_SENT.search(s):
            if "travel_start" not in facts and "travel_end" not in facts:
                a, b = _range_in(s, pub)
                if a or b:
                    facts["travel_start"], facts["travel_end"] = a, b
                    evidence["travel"] = _snippet(s, _TRAVEL_SENT.search(s).group(0))
            continue
        if _SALE_SENT.search(s) and "sale_start" not in facts and "sale_end" not in facts:
            a, b = extract_dates(s, pub)
            if a or b:
                facts["sale_start"], facts["sale_end"] = a, b
                m = _DATE.search(s)
                evidence["sale"] = _snippet(s, m.group(0) if m else None)
        if "discount" not in facts:
            d = extract_discount(s)
            if d:
                facts["discount"] = d
                evidence["discount"] = _snippet(s, re.match(r"최대|[\d,]+만?", d).group(0))
        if "destination" not in facts:
            o, dst = airports(s)
            if dst:
                facts["origin"], facts["destination"] = o, dst
                evidence["route"] = _snippet(s, dst.split("(")[0])
    return facts, evidence


# ---------------------------------------------------------------- 해외 호텔 (2026-10-15 시범)

# 해외 지명. 제목에 있으면 그 숙박 행사를 '해외'로 본다. '18개국'처럼 나라 수가 나와도 해외
_OVERSEAS = ["일본", "도쿄", "오사카", "교토", "후쿠오카", "오키나와", "삿포로", "홋카이도", "규슈", "사가현", "나고야",
             "대만", "타이베이", "홍콩", "마카오", "중국", "상하이", "베이징", "싱가포르", "베트남", "다낭", "나트랑", "푸꾸옥",
             "하노이", "호찌민", "태국", "방콕", "푸껫", "치앙마이", "필리핀", "세부", "보라카이", "말레이시아", "코타키나발루",
             "인도네시아", "발리", "괌", "사이판", "하와이", "미국", "유럽", "두바이", "몰디브", "호주", "해외"]
_OVERSEAS_RE = re.compile("|".join(sorted(map(re.escape, _OVERSEAS), key=len, reverse=True)) + r"|\d+\s?개국")
_DOMESTIC_REGIONS = [r for r in _REGIONS if r not in _OVERSEAS]


def hotel_scope(title, regions=None):
    """'overseas' | 'domestic' | None — 숙박 행사의 지역. 해외 지명이 하나라도 있으면 해외."""
    if _OVERSEAS_RE.search(_mask_airlines(title)):
        return "overseas"
    if any(r in _DOMESTIC_REGIONS for r in (regions or [])):
        return "domestic"
    return None


# 특정 행사가 아니라 업계 동향·모음 기사 (2026-10-15 시범 첫 수집에서 걸린 '짧은 연휴 어디로 갈까…국내 숙박 할인·일본 소도시 여행 경쟁')
_TREND = re.compile(r"경쟁|어디로|동향|트렌드|총정리|방법|국내\s?숙박")


def is_overseas_hotel_sale(title):
    """브랜드가 없어도 해외 숙박 할인 기사로 볼 수 있는가 (예: '괌 호텔 5곳 공동 프로모션').
    브랜드가 있는 기사는 is_hotel_sale만 따른다 ('대구 메리어트 호텔, 베트남 미식 여행 프로모션'은 국내 호텔 행사)."""
    return bool(_HOTEL_CONTEXT.search(title) and (_HOTEL_SALE.search(title) or "프로모션" in title)
                and _OVERSEAS_RE.search(_mask_airlines(title)) and not _HOTEL_NOISE.search(title)
                and not _TREND.search(title) and not airlines_in(title) and not hotels_in(title))


# 영어 기사: 번역하지 않는다. 가격 할인이 분명한 것만 받고, 할인율·기간·지역만 규칙으로 뽑아 한국어 칸에 넣는다.
# 규칙은 2026-10-15 영어판 Google 뉴스 '호텔 할인' 검색 결과 23건을 읽고 정했다 (대부분 포인트 적립·매각·승진 기사)
_EN_CTX = re.compile(r"\b(?:hotels?|resorts?|stays?|rooms?|accommodation)\b", re.I)
_EN_PRICE = re.compile(r"\d{1,2}\s?%\s?off|up to \d{1,2}\s?%|save \d{1,2}\s?%|\d{1,2}\s?% discount|flash sale|"
                       r"travel sale|discount code|promo code|half[- ]price|black friday|cyber monday", re.I)
_EN_NOISE = re.compile(r"\bpoints?\b|\bmiles\b|\bbonus\b|\bstatus\b|\belite\b|leadership|appoint|for sale|\bsells?\b|\bsold\b|"
                       r"acquir|\bstake\b|lawsuit|appeal|credit card|\bstock\b|\bshares\b|\bIPO\b|merger|layoff|\bstrike\b|\bearn\b|"
                       # 포인트 숙박 할인, 박람회, 할인 코드 모음 페이지 (2026-10-15 시범 첫 수집에서 걸린 유형)
                       r"\baward\b|\bexpo\b|\bfair\b|(?:discount|promo|voucher) codes?\s?(?:\d{4}|:)|coupons? for", re.I)
_EN_PLACES = {"Asia Pacific": "아시아·태평양", "Latin America": "중남미", "Hong Kong": "홍콩", "Japan": "일본", "Tokyo": "도쿄",
              "Osaka": "오사카", "Kyoto": "교토", "Okinawa": "오키나와", "Singapore": "싱가포르", "Bali": "발리", "Thailand": "태국",
              "Bangkok": "방콕", "Phuket": "푸껫", "Vietnam": "베트남", "Macau": "마카오", "Taiwan": "대만", "Guam": "괌",
              "Hawaii": "하와이", "Maldives": "몰디브", "Dubai": "두바이", "Philippines": "필리핀", "Malaysia": "말레이시아",
              "Indonesia": "인도네시아", "Australia": "호주", "Europe": "유럽", "Caribbean": "카리브", "Mexico": "멕시코",
              "Canada": "캐나다", "Asia": "아시아", "Korea": "한국", "Seoul": "서울"}
_EN_PLACE_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _EN_PLACES), key=len, reverse=True)) + r")\b")
_EN_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_EN_MONTH = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
_EN_RANGE = re.compile(_EN_MONTH + r"\s(\d{1,2})\s?(?:[-–]|to|through)\s?(?:" + _EN_MONTH + r"\s)?(\d{1,2})\b", re.I)
_EN_UNTIL = re.compile(r"\b(?:until|through|thru|ends?|by)\s" + _EN_MONTH + r"\s(\d{1,2})\b", re.I)


def is_hotel_sale_en(title):
    return bool(_EN_CTX.search(title) and _EN_PRICE.search(title) and not _EN_NOISE.search(title))


def _en_date(mon, day, pub):
    try:
        mo = _EN_MONTHS[mon[:3].lower()]
        d = date(pub.year, mo, int(day))
        return date(pub.year + 1, mo, int(day)) if d < pub - timedelta(days=60) else d
    except (KeyError, ValueError):
        return None


def extract_dates_en(title, pub):
    m = _EN_RANGE.search(title)
    if m:
        a = _en_date(m.group(1), m.group(2), pub)
        b = _en_date(m.group(3) or m.group(1), m.group(4), pub)
        if a and b and b >= a:
            return a, b
    m = _EN_UNTIL.search(title)
    if m:
        return None, _en_date(m.group(1), m.group(2), pub)
    return None, None


def extract_discount_en(title):
    m = re.search(r"(\d{1,2})\s?%\s?to\s?(\d{1,2})\s?%\s?off", title, re.I) or re.search(r"up to (\d{1,2})\s?%", title, re.I)
    if m:
        return f"최대 {m.group(m.lastindex)}%"
    m = re.search(r"(\d{1,2})\s?%\s?(?:off|discount)|save (\d{1,2})\s?%", title, re.I)
    if m:
        return f"{m.group(1) or m.group(2)}% 할인"
    return None


def regions_en(title):
    out = []
    for m in _EN_PLACE_RE.finditer(title):
        r = _EN_PLACES[m.group(1)]
        if r not in out:
            out.append(r)
    return out
