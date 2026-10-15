"""기사 제목에서 항공사·판매 기간·할인 정보·인천 출발 여부를 뽑는다.

날짜는 기사 발행일(KST)을 기준으로 해석한다. 제목에 연도가 거의 안 나오므로
월/연도는 발행일에서 추정한다.
"""

import re
from datetime import date, timedelta

from .airlines import AIRLINES

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


_ALIASES = sorted(
    ((a["id"], alias, _alias_pattern(alias)) for a in AIRLINES for alias in a["aliases"]),
    key=lambda x: -len(x[1]),
)


def detect_airline(title):
    """제목에서 가장 먼저 나오는 항공사 id. 같은 위치면 긴 표기가 이긴다."""
    best = None  # (pos, -len, id)
    for airline_id, alias, pat in _ALIASES:
        m = pat.search(title)
        if m:
            cand = (m.start(), -len(alias), airline_id)
            if best is None or cand < best:
                best = cand
    return best[2] if best else None


# ---------------------------------------------------------------- 특가 기사 판별

# 이 말이 있으면 그 자체로 항공권 특가 기사
_SALE_STRONG = re.compile(r"특가|얼리버드|세일|SALE|Sale|반값")
# 이 말은 기내식·호텔·카드 할인에도 쓰여서 항공권 맥락이 같이 있어야 한다
_SALE_WEAK = re.compile(r"할인|프로모션|이벤트")
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
_TRAVEL_AFTER = re.compile(r"^.{0,8}?(?:탑승|출발편|출발|여행|운항|취항|직항)")
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
    return None


# ---------------------------------------------------------------- 인천 출발

_OTHER_ORIGIN = re.compile(r"(김포|김해|부산|대구|청주|무안|양양|광주|제주)\s?(?:출발|발\b|[-~–])")


def icn_flag(title):
    """'yes' | 'no' | 'unknown'"""
    if re.search(r"인천|ICN", title):
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
