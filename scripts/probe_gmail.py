"""Gmail 연결 확인과 항공사 메일 현황 (메일 수집 1단계 사전 검증).

python -m scripts.probe_gmail [일수]   # 환경변수 GMAIL_USER, GMAIL_APP_PASSWORD 필요. 기본 30일

항공사 발신 도메인에서 온 메일만 검색한다(collector.sources.gmail_imap.SEARCH_DOMAINS). Actions 로그가 공개라서
항공사별 메일 수, 발신 인증(DKIM·DMARC) 통과 수, 제목에 특가 표현이 있는 메일 수, 발신 도메인만 출력한다.
제목·본문·주소는 출력하지 않는다.
"""

import sys
from collections import Counter, defaultdict

from collector.sources.gmail_imap import SEARCH_DOMAINS, airline_of, authenticated, connect, recent_headers

PROMO = ("특가", "할인", "세일", "프로모션", "쿠폰", "이벤트", "sale", "deal", "offer", "% off", "fare")

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
imap = connect()
if imap is None:
    sys.exit("GMAIL_USER / GMAIL_APP_PASSWORD가 없습니다.")
try:
    box, rows = recent_headers(imap, days)
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
