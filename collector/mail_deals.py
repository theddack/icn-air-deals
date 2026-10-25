"""항공사 뉴스레터(Gmail) → 행사 기사 data/mail_articles.json.

python -m collector.mail_deals   # 환경변수 GMAIL_USER, GMAIL_APP_PASSWORD (없으면 건너뛴다)

- 대상: 항공사 발신 도메인으로 판별되고(보낸 사람 이름만 맞는 메일은 제외) Gmail이 붙인 DKIM·DMARC 결과로
  발신 인증을 통과한 메일만. 그래서 이 기사가 들어간 행사는 '항공사 공식 확인'으로 표시한다.
- 공개 저장소에 올라가므로 본문은 메모리에서만 읽는다. 남기는 것은 개인 정보를 지운 제목, 메일 날짜, 본문에서
  뽑은 사실값(판매·탑승 기간, 할인, 도착지)뿐이다. 근거 구절·메일 속 링크(개인 추적 토큰)·쿠폰 코드·수신자
  정보는 저장하지 않는다. 링크는 항공사 공식 사이트로 둔다. Actions 로그에는 개수만 찍는다.
- 행사 판정은 뉴스와 같은 규칙(extract.category_of)을 '항공사 제목'에 적용하고, 본문 사실값이 하나 이상 있어야 한다.
- 실패해도 이전 파일을 그대로 두고 0으로 끝낸다 (뉴스 수집·배포는 계속).
"""

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import extract
from .airlines import AIRLINES
from .sources import gmail_imap as gm
from .status import KST, today_kst

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "mail_articles.json"
STATS = ROOT / "data" / "mail_stats.json"  # 단계별 메일 개수만 (제목·주소 없음)
DAYS = 21          # 한 번에 살펴볼 최근 메일 기간
KEEP_DAYS = 45     # 뉴스 기사 보관 기간과 같다
BODY_MAX = 6000    # 본문 앞부분만 본다 (행사 안내는 위쪽에 있다)

OFFICIAL = {a["name"]: a["official_url"] for a in AIRLINES}

# 제목에서 지울 것: 광고 표기, 수신자 이름('홍길동님'), 메일 주소, 주소(URL), 6자리 이상 숫자(회원·예약 번호), 쿠폰 코드처럼 보이는 영숫자
_AD = re.compile(r"^\s*[(\[]\s*광고\s*[)\]]\s*")
_PRIVATE = [re.compile(p) for p in (r"\S+@\S+", r"https?://\S+", r"[가-힣A-Za-z]{1,10}\s?님(?![가-힣])", r"\d{6,}",
                                     r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6,}\b")]


def clean_subject(subject):
    s = _AD.sub("", subject or "")
    for p in _PRIVATE:
        s = p.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,·-:|")
    return s[:120]


def mail_article(airline, subject, body, sent, message_id, now_iso, why=None):
    """인증된 항공사 메일 한 통 → 행사 기사 dict, 행사 메일이 아니면 None. 본문은 돌려주지 않는다.
    why(Counter)를 주면 걸러진 단계를 센다: not_listed / not_sale_subject / no_facts."""
    why = why if why is not None else Counter()
    official = OFFICIAL.get(airline)
    if not official:  # airlines.py에 없는 항공사(춘추항공 등)는 행사 묶기·화면 링크를 만들 수 없어 건너뛴다
        why["not_listed"] += 1
        return None
    subj = clean_subject(subject)
    title = f"{airline} {subj}" if airline not in subj else subj
    if extract.category_of(title) != "flight":
        why["not_sale_subject"] += 1
        return None
    pub = (sent.astimezone(KST) if sent and sent.tzinfo else (sent or datetime.now(KST))).date()
    facts, _ = extract.facts_from_summary(f"{subj}. {(body or '')[:BODY_MAX]}".replace("\n", ". "), pub)
    if not facts:
        why["no_facts"] += 1
        return None
    mail_id = hashlib.sha256((message_id or f"{airline}{subject}{pub}").encode("utf-8")).hexdigest()[:16]
    url = f"{official}#mail-{mail_id}"  # 기사마다 주소가 달라야 중복 제거에 걸리지 않는다 (링크는 공식 사이트)
    fields = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in facts.items()}
    return {"title": title, "outlet": f"{airline} 메일", "url": url, "published": pub.isoformat(), "first_seen": now_iso,
            "source": "mail", "mail_id": mail_id,
            # 근거 구절은 남기지 않는다 (본문 문장에 이름·쿠폰이 섞일 수 있다)
            "summary_facts": {"url": url, "outlet": f"{airline} 메일", "label": "본문", "fields": fields,
                              "evidence": {g: "" for g in ("sale", "travel", "discount", "route")}}}


def merge(previous, new, today):
    by_id = {a["mail_id"]: a for a in previous}
    added = 0
    for a in new:
        if a["mail_id"] not in by_id:
            by_id[a["mail_id"]] = a
            added += 1
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    kept = sorted((a for a in by_id.values() if a["published"] >= cutoff), key=lambda a: a["published"], reverse=True)
    return kept, added


def collect(imap, now_iso):
    """→ (기사 목록, 단계별 개수). 본문은 이 함수 안에서만 쓴다.
    개수만 공개 파일(mail_stats.json)에 남긴다 — 로그를 못 봐도 어느 단계에서 걸러졌는지 알 수 있게."""
    _, rows = gm.recent_headers(imap, DAYS)
    out, seen, why = [], set(), Counter(searched=len(rows))
    for r in rows:
        name, domain, basis = gm.airline_of(r["from"])
        key = r["message_id"] or r["uid"]
        if key in seen:
            why["duplicate"] += 1
            continue
        seen.add(key)
        if not name or basis != "domain" or not r["uid"]:
            why["not_airline_domain"] += 1
            continue
        if not gm.authenticated(r["auth"], domain):
            why["not_authenticated"] += 1
            continue
        why["checked"] += 1
        try:
            a = mail_article(name, r["subject"], gm.message_text(imap, r["uid"]), r["date"], r["message_id"], now_iso, why)
        except Exception as e:  # 한 통 실패로 전체를 멈추지 않는다. 오류 종류만 남긴다
            why["read_error"] += 1
            print(f"[mail_deals] 메일 한 통 읽기 실패: {type(e).__name__}", file=sys.stderr)
            continue
        if a:
            why["accepted"] += 1
            out.append(a)
    return out, why


def main():
    now = datetime.now(KST)
    try:
        imap = gm.connect()
    except Exception as e:
        print(f"[mail_deals] Gmail 연결 실패, 이전 파일 유지: {type(e).__name__}", file=sys.stderr)
        return 0
    if imap is None:
        print("[mail_deals] GMAIL_USER / GMAIL_APP_PASSWORD 없음 — 건너뜁니다.")
        return 0
    try:
        new, why = collect(imap, now.isoformat(timespec="seconds"))
    except Exception as e:
        print(f"[mail_deals] 메일 수집 실패, 이전 파일 유지: {type(e).__name__}", file=sys.stderr)
        return 0
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        previous = []
    kept, added = merge(previous, new, today_kst())
    OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    STATS.write_text(json.dumps({"checked_at": now.isoformat(timespec="seconds"), "days": DAYS, **dict(why), "kept": len(kept)},
                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[mail_deals] {dict(why)} · 새로 {added} · 보관 {len(kept)}통")
    return 0


if __name__ == "__main__":
    sys.exit(main())
