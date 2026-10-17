"""Gmail에서 항공사가 보낸 메일을 읽는다 (IMAP, 읽기 전용).

- 계정은 환경변수 GMAIL_USER / GMAIL_APP_PASSWORD(레포 Secrets, 구글 앱 비밀번호). 없으면 아무것도 하지 않는다.
- 공개 저장소이고 Actions 로그도 공개라서 메일 원문, 메일 속 링크(개인 추적 토큰이 붙는다), 항공사가 아닌
  발신자는 저장하지도 출력하지도 않는다.
- 메일함은 EXAMINE(읽기 전용)으로 열고 본문도 PEEK로 받아서 읽음 표시·삭제를 하지 않는다.
- 항공사 판별: 보낸 주소 도메인이 공식 사이트 도메인과 같거나 그 하위 도메인이면, 또는 도메인 라벨 중 하나가
  공식 도메인의 핵심 이름(jejuair, flypeach, jal …)과 같으면 그 항공사. 그래도 못 정하면 표시 이름에 항공사
  aliases가 있는지 본다. 공식 사이트와 다른 도메인으로 보내는 곳은 EXTRA_DOMAINS에 적는다.
"""

import email
import imaplib
import os
import re
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import urlparse

from ..airlines import AIRLINES

HOST = "imap.gmail.com"
BATCH = 200

# airlines.py에 아직 없지만 메일을 받기로 한 항공사(2026-10-17 가입), 공식 사이트와 다른 발신 도메인
EXTRA_DOMAINS = [
    ("춘추항공", ["ch.com"]),
    ("홍콩익스프레스", ["hkexpress.com"]),
    ("에어마카오", ["airmacau.com.mo"]),
    ("에어로몽골리아", ["aeromongolia.com"]),
    ("스칸디나비아항공", ["flysas.com"]),
    ("해남항공", ["hainanairlines.com"]),
]

_TWO_LEVEL = {"co.kr", "co.jp", "co.uk", "com.mo", "com.my", "com.au", "com.tw", "com.hk", "com.cn", "co.nz"}


def _host(url):
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _core(host):
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL:
        return labels[-3]
    return labels[-2] if len(labels) >= 2 else host


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


def decode(value):
    try:
        return str(make_header(decode_header(value or "")))
    except (UnicodeDecodeError, LookupError):
        return value or ""


def airline_of(from_header):
    """From 헤더 → (항공사 이름 또는 None, 보낸 주소 도메인)."""
    display, addr = parseaddr(decode(from_header))
    domain = addr.rpartition("@")[2].lower()
    labels = domain.split(".")[:-1]
    for name, hosts, cores, _ in RULES:
        if any(domain == h or domain.endswith("." + h) for h in hosts):
            return name, domain
    for name, hosts, cores, _ in RULES:
        if any(c in labels for c in cores):
            return name, domain
    for name, _, _, aliases in RULES:
        for al in aliases:
            hit = re.search(rf"(?<![A-Za-z]){re.escape(al)}(?![A-Za-z])", display) if al.isascii() else al in display
            if hit:
                return name, domain
    return None, domain


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


def recent_headers(imap, days):
    """최근 days일 메일의 보낸 사람·제목·날짜. Gmail 검색(X-GM-RAW)을 쓴다."""
    box = all_mail_box(imap)
    imap.select(box, readonly=True)
    _, data = imap.uid("SEARCH", "X-GM-RAW", f'"newer_than:{days}d"')
    uids = data[0].split() if data and data[0] else []
    out = []
    for i in range(0, len(uids), BATCH):
        chunk = b",".join(uids[i:i + BATCH]).decode()
        _, rows = imap.uid("FETCH", chunk, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        for row in rows:
            if not isinstance(row, tuple):
                continue
            msg = email.message_from_bytes(row[1])
            try:
                sent = parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
            except (TypeError, ValueError):
                sent = None
            out.append({"from": msg["From"] or "", "subject": decode(msg["Subject"]), "date": sent})
    return box, out
