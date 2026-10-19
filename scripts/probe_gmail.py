"""Gmail 연결 확인과 항공사 메일 현황 (메일 수집 1단계 사전 검증).

python -m scripts.probe_gmail [일수]   # 환경변수 GMAIL_USER, GMAIL_APP_PASSWORD 필요. 기본 30일

항공사 발신 도메인에서 온 메일만 검색한다(collector.sources.gmail_imap.SEARCH_DOMAINS). Actions 로그가 공개라서
항공사별 메일 수, 발신 인증(DKIM·DMARC) 통과 수, 제목에 특가 표현이 있는 메일 수, 발신 도메인만 출력한다.
제목·본문·주소는 출력하지 않는다.

본문 측정(2026-10-19 추가): 인증을 통과한 항공사 메일의 본문을 메모리에서만 읽어, 금액·판매 기간·탑승 기간·할인율·
도착지가 들어 있는 메일이 몇 통인지 센다(collector.sources.gmail_imap.promo_signals). 값은 출력하지 않는다.
"""

import sys
from collections import Counter, defaultdict
from datetime import datetime

from collector.sources.gmail_imap import (SEARCH_DOMAINS, airline_of, authenticated, connect, message_text, promo_signals,
                                         recent_headers)

PROMO = ("특가", "할인", "세일", "프로모션", "쿠폰", "이벤트", "sale", "deal", "offer", "% off", "fare")

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
imap = connect()
if imap is None:
    sys.exit("GMAIL_USER / GMAIL_APP_PASSWORD가 없습니다.")
SIGNALS = [("price_krw", "원화 금액"), ("price_foreign", "외화 금액"), ("sale", "판매 기간"), ("travel", "탑승 기간"),
           ("discount", "할인율"), ("route", "도착지"), ("ad", "(광고) 제목")]
signals = defaultdict(Counter)
try:
    box, rows = recent_headers(imap, days)
    seen_body = set()
    for r in rows:
        name, domain, basis = airline_of(r["from"])
        key = r["message_id"] or r["uid"]
        if not (name and basis == "domain" and authenticated(r["auth"], domain) and r["uid"]) or key in seen_body:
            continue
        seen_body.add(key)
        try:
            got = promo_signals(r["subject"], message_text(imap, r["uid"]), (r["date"] or datetime.now()).date())
        except Exception as e:  # 한 통 실패로 측정 전체를 멈추지 않는다. 오류 종류만 남긴다
            signals[name]["error:" + type(e).__name__] += 1
            continue
        signals[name]["mails"] += 1
        for k in got:
            signals[name][k] += 1
        if got & {"price_krw", "price_foreign", "sale", "discount"}:
            signals[name]["any"] += 1
finally:
    imap.logout()

print(f"로그인 성공 · 메일함 {box} · 항공사 발신 도메인 {len(SEARCH_DOMAINS)}곳으로 검색 · 최근 {days}일 {len(rows)}통")
per, verified, promo, domains = Counter(), Counter(), Counter(), defaultdict(Counter)
name_only, unknown = Counter(), 0
seen = set()
dupes = 0
for r in rows:
    if r["message_id"]:
        if r["message_id"] in seen:
            dupes += 1
            continue
        seen.add(r["message_id"])
    name, domain, basis = airline_of(r["from"])
    if not name:
        unknown += 1
        continue
    if basis == "name":
        name_only[name] += 1
        continue
    per[name] += 1
    domains[name][domain] += 1
    if authenticated(r["auth"], domain):
        verified[name] += 1
    if any(w in r["subject"].lower() for w in PROMO):
        promo[name] += 1

print(f"항공사 메일 {sum(per.values())}통 (발신 인증 통과 {sum(verified.values())}) · 중복 {dupes} · "
      f"이름만 일치(검증 필요) {sum(name_only.values())} · 판별 못 함 {unknown}\n")
for name, n in per.most_common():
    doms = ", ".join(f"{d}({c})" for d, c in domains[name].most_common())
    print(f"- {name}: {n}통, 인증 통과 {verified[name]}, 제목에 특가 표현 {promo[name]} · 발신 도메인 {doms}")
for name, n in name_only.most_common():
    print(f"- (검증 필요) 보낸 사람 이름만 '{name}': {n}통")

total = Counter()
for c in signals.values():
    total.update(c)
print(f"\n본문 측정: 인증 통과 메일 {total['mails']}통 중 금액·판매 기간·할인율 중 하나라도 있는 메일 {total['any']}통")
print("  " + " · ".join(f"{label} {total[k]}" for k, label in SIGNALS))
for name, c in sorted(signals.items(), key=lambda kv: -kv[1]["mails"]):
    errs = sum(v for k, v in c.items() if k.startswith("error:"))
    print(f"- {name}: {c['mails']}통, 행사 정보 {c['any']} · " + " · ".join(f"{label} {c[k]}" for k, label in SIGNALS if c[k])
          + (f" · 읽기 실패 {errs}" if errs else ""))
