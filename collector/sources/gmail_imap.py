"""Gmail에서 항공사가 보낸 메일을 읽는다 (IMAP, 읽기 전용).

- 계정은 환경변수 GMAIL_USER / GMAIL_APP_PASSWORD(레포 Secrets, 구글 앱 비밀번호). 없으면 아무것도 하지 않는다.
- 공개 저장소이고 Actions 로그도 공개라서 메일 원문, 메일 속 링크(개인 추적 토큰이 붙는다), 개인별 쿠폰 코드는
  저장하지도 출력하지도 않는다.
- 개인 메일은 아예 가져오지 않는다. Gmail 검색을 항공사 발신 도메인(SEARCH_DOMAINS)으로 좁혀서 그 메일의
  헤더만 받는다. 메일함은 EXAMINE(읽기 전용)으로 열고 PEEK로 받아 읽음 표시·삭제를 하지 않는다.
- 항공사 판별(airline_of): 보낸 주소 도메인이 공식 도메인과 같거나 하위 도메인이면, 또는 도메인 라벨 중 하나가
  공식 도메인의 핵심 이름(jejuair, flypeach …)과 같으면 그 항공사("domain"). 표시 이름에 항공사 이름만 있는
  경우("name")는 누구나 이름을 바꿀 수 있어서 검증 필요로 따로 둔다.
- 발신 인증(authenticated): Gmail(mx.google.com)이 붙인 Authentication-Results에서 DKIM 서명 도메인이나
  DMARC 통과 도메인이 보낸 주소 도메인과 같은 조직일 때만 통과. 사이트에 '항공사 메일 확인'으로 올릴 수 있는
  메일은 판별 "domain" + 인증 통과인 것뿐이다.
"""

import email
import html
import imaplib
import os
import re
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import urlparse

from ..airlines import AIRLINES

HOST = "imap.gmail.com"
BATCH = 200

# 공식 사이트 도메인과 다른 발신 도메인, airlines.py에 아직 없지만 메일을 받기로 한 항공사(2026-10-17 가입)
# probe-gmail 첫 실행(2026-10-17)에서 airmacau.com.cn, infos-klm.com을 확인했다
EXTRA_DOMAINS = [
    ("KLM", ["infos-klm.com"]),
    ("일본항공", ["jal.com"]),
    ("춘추항공", ["ch.com"]),
    ("홍콩익스프레스", ["hkexpress.com"]),
    ("에어마카오", ["airmacau.com.mo", "airmacau.com.cn"]),
    ("에어로몽골리아", ["aeromongolia.com"]),
    ("스칸디나비아항공", ["flysas.com"]),
    ("해남항공", ["hainanairlines.com"]),
    # 항공권 가격 비교(메타서치) 이벤트 메일 (2026-10-25 가입). 이름은 hotels.py의 플랫폼 이름과 같게 둔다
    ("스카이스캐너", ["skyscanner.net", "skyscanner.com", "skyscanner.co.kr"]),
    ("카약", ["kayak.com", "kayak.co.kr"]),
]

_TWO_LEVEL = {"co.kr", "co.jp", "co.uk", "com.mo", "com.my", "com.au", "com.tw", "com.hk", "com.cn", "co.nz"}


def _host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _labels_root(host):
    """공개 접미사 바로 앞까지: kr.ceair.com → (ceair, ceair.com), www.jal.co.jp → (jal, jal.co.jp)."""
    labels = host.split(".")
    n = 3 if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL else 2
    root = labels[-n:] if len(labels) >= n else labels
    return root[0], ".".join(root)


def _core(host):
    return _labels_root(host)[0]


def registrable(host):
    return _labels_root(host)[1]


def _rules():
    rules = []  # (항공사 이름, 공식 도메인들, 핵심 이름들, aliases)
    for a in AIRLINES:
        host = _host(a["official_url"])
        core = _core(host)
        rules.append((a["name"], [host], [core] if len(core) >= 3 else [], a["aliases"]))
    for name, hosts in EXTRA_DOMAINS:
        rules.append((name, hosts, [c for c in map(_core, hosts) if len(c) >= 3], [name]))
    return rules


RULES = _rules()
SEARCH_DOMAINS = sorted({registrable(h) for _, hosts, _, _ in RULES for h in hosts})


def decode(value):
    try:
        return str(make_header(decode_header(value or "")))
    except (UnicodeDecodeError, LookupError):
        return value or ""


def airline_of(from_header):
    """From 헤더 → (항공사 이름 또는 None, 보낸 주소 도메인, 판별 근거 "domain"·"name"·None)."""
    display, addr = parseaddr(decode(from_header))
    domain = addr.rpartition("@")[2].lower()
    labels = domain.split(".")[:-1]
    for name, hosts, cores, _ in RULES:
        if any(domain == h or domain.endswith("." + h) for h in hosts):
            return name, domain, "domain"
    for name, hosts, cores, _ in RULES:
        if any(c in labels for c in cores):
            return name, domain, "domain"
    for name, _, _, aliases in RULES:
        for al in aliases:
            hit = re.search(rf"(?<![A-Za-z]){re.escape(al)}(?![A-Za-z])", display) if al.isascii() else al in display
            if hit:
                return name, domain, "name"
    return None, domain, None


_DKIM = re.compile(r"\bdkim=pass\b[^;]*?\bheader\.(?:d=|i=@?)([\w.-]+)", re.I)
_DMARC = re.compile(r"\bdmarc=pass\b[^;]*?\bheader\.from=([\w.-]+)", re.I)


def authenticated(auth_results, domain):
    """Gmail이 붙인 Authentication-Results 중 DKIM·DMARC 통과 도메인이 보낸 주소와 같은 조직이면 True.

    다른 서버가 붙인 헤더는 보낸 쪽이 꾸며 넣을 수 있어서 mx.google.com이 붙인 것만 본다.
    """
    if not domain:
        return False
    base = registrable(domain)
    for h in auth_results or []:
        s = " ".join(str(h).split())
        if not s.lower().startswith("mx.google.com"):
            continue
        for d in _DKIM.findall(s) + _DMARC.findall(s):
            if registrable(d.lower().strip(".")) == base:
                return True
    return False


def connect():
    user, password = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not password:
        return None
    imap = imaplib.IMAP4_SSL(HOST)
    imap.login(user, password.replace(" ", ""))
    return imap


def all_mail_box(imap):
    """'전체보관함'은 계정 언어에 따라 이름이 달라서 \\All 표시로 찾는다. 못 찾으면 받은편지함."""
    _, lines = imap.list()
    for line in lines or []:
        if line and b"\\All" in line:
            m = re.search(rb'"([^"]+)"\s*$', line) or re.search(rb"(\S+)\s*$", line)
            if m:
                return '"' + m.group(1).decode() + '"'
    return "INBOX"


def special_box(imap, flag):
    """\\Junk(스팸함)·\\Trash 같은 특수 메일함 이름. 계정 언어에 따라 이름이 달라 표시로 찾는다. 없으면 None."""
    _, lines = imap.list()
    for line in lines or []:
        if line and flag.encode() in line:
            m = re.search(rb'"([^"]+)"\s*$', line) or re.search(rb"(\S+)\s*$", line)
            if m:
                return '"' + m.group(1).decode() + '"'
    return None


def count_in(imap, box, days):
    """그 메일함에서 최근 days일 항공사 발신 도메인 메일 수 (헤더도 받지 않고 개수만)."""
    if not box:
        return None
    imap.select(box, readonly=True)
    _, data = imap.uid("SEARCH", "X-GM-RAW", f'"{search_query(days)}"')
    return len(data[0].split()) if data and data[0] else 0


def search_query(days):
    return f"newer_than:{days}d from:({' OR '.join(SEARCH_DOMAINS)})"


def recent_headers(imap, days):
    """최근 days일 동안 항공사 발신 도메인에서 온 메일의 헤더(보낸 사람·제목·날짜·Message-ID·인증 결과)."""
    box = all_mail_box(imap)
    imap.select(box, readonly=True)
    _, data = imap.uid("SEARCH", "X-GM-RAW", f'"{search_query(days)}"')
    uids = data[0].split() if data and data[0] else []
    out = []
    fields = "FROM SUBJECT DATE MESSAGE-ID AUTHENTICATION-RESULTS"
    for i in range(0, len(uids), BATCH):
        chunk = b",".join(uids[i:i + BATCH]).decode()
        _, rows = imap.uid("FETCH", chunk, f"(BODY.PEEK[HEADER.FIELDS ({fields})])")
        for row in rows:
            if not isinstance(row, tuple):
                continue
            m = re.search(rb"UID (\d+)", row[0])
            msg = email.message_from_bytes(row[1])
            try:
                sent = parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
            except (TypeError, ValueError):
                sent = None
            out.append({"uid": m.group(1).decode() if m else None, "from": msg["From"] or "", "subject": decode(msg["Subject"]), "date": sent,
                        "message_id": (msg["Message-ID"] or "").strip(),
                        "auth": msg.get_all("Authentication-Results") or []})
    return box, out


def _html_text(s):
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|td|li|h\d)>", "\n", s)
    return html.unescape(re.sub(r"<[^>]+>", " ", s))


def message_text(imap, uid):
    """메일 본문을 글자만 남겨 돌려준다(PEEK이라 읽음 표시가 바뀌지 않는다). 메모리에서만 쓰고 저장·출력하지 않는다.
    text/plain이 있으면 그것을, 없으면 text/html에서 태그를 지운 것을 쓴다."""
    _, rows = imap.uid("FETCH", uid, "(BODY.PEEK[])")
    raw = next((r[1] for r in rows or [] if isinstance(r, tuple)), None)
    if not raw:
        return ""
    msg = email.message_from_bytes(raw)
    plain, htm = [], []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html") or part.get_filename():
            continue
        try:
            text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except (LookupError, AttributeError):
            continue
        (plain if ctype == "text/plain" else htm).append(text)
    text = "\n".join(plain) if plain else _html_text("\n".join(htm))
    return re.sub(r"[ \t\u00a0\u200b]+", " ", text)


_KRW = re.compile(r"(?:₩|KRW)\s?\d[\d,]{3,}|\d{1,3}(?:,\d{3})+\s?원|\d+\s?만\s?\d{0,4}\s?원")
_FOREIGN = re.compile(r"(?:US\$|HK\$|NT\$|S\$|\$|¥|€|£)\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|JPY|EUR|HKD|TWD|SGD|엔|달러)\b")
_AD_PREFIX = re.compile(r"^\s*[(\[]\s*광고\s*[)\]]")


def promo_signals(subject, text, pub):
    """메일 한 통에서 행사 정보가 있는지(측정용) → 들어 있는 항목 이름 집합. 값은 돌려주지 않는다.

    price_krw 원화 금액 / price_foreign 외화 금액 / sale 판매 기간 / travel 탑승 기간 / discount 할인율 / route 도착지
    ad 제목 앞 '(광고)' (국내 광고 메일은 법으로 붙인다)"""
    from ..extract import facts_from_summary  # 측정 때만 쓴다
    got = set()
    body = f"{subject}\n{text or ''}"
    if _KRW.search(body):
        got.add("price_krw")
    if _FOREIGN.search(body):
        got.add("price_foreign")
    facts, _ = facts_from_summary(body.replace("\n", ". "), pub)
    for k, f in (("sale", ("sale_start", "sale_end")), ("travel", ("travel_start", "travel_end")),
                 ("discount", ("discount",)), ("route", ("destination",))):
        if any(facts.get(x) for x in f):
            got.add(k)
    if _AD_PREFIX.match(subject or ""):
        got.add("ad")
    return got
