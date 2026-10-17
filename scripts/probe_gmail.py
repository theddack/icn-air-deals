"""Gmail 연결 확인과 항공사 메일 현황 (메일 수집 1단계 사전 검증).

python -m scripts.probe_gmail [일수]   # 환경변수 GMAIL_USER, GMAIL_APP_PASSWORD 필요. 기본 30일

Actions 로그가 공개라서 항공사별 메일 수, 발신 도메인, 제목에 특가 표현이 있는 메일 수만 출력한다.
제목·본문·주소, 항공사가 아닌 발신자의 도메인은 출력하지 않는다.
"""

import sys
from collections import Counter, defaultdict

from collector.sources.gmail_imap import airline_of, connect, recent_headers

PROMO = ("특가", "할인", "세일", "프로모션", "쿠폰", "이벤트", "sale", "deal", "offer", "% off", "fare")

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
imap = connect()
if imap is None:
    sys.exit("GMAIL_USER / GMAIL_APP_PASSWORD가 없습니다.")
try:
    box, rows = recent_headers(imap, days)
finally:
    imap.logout()

print(f"로그인 성공 · 메일함 {box} · 최근 {days}일 메일 {len(rows)}통")
per, domains, promo = Counter(), defaultdict(Counter), Counter()
others = 0
for r in rows:
    name, domain = airline_of(r["from"])
    if not name:
        others += 1
        continue
    per[name] += 1
    domains[name][domain] += 1
    if any(w in r["subject"].lower() for w in PROMO):
        promo[name] += 1

print(f"항공사 메일 {sum(per.values())}통 · 항공사가 아닌 메일 {others}통(내용 출력 안 함)\n")
for name, n in per.most_common():
    doms = ", ".join(f"{d}({c})" for d, c in domains[name].most_common())
    print(f"- {name}: {n}통, 제목에 특가 표현 {promo[name]}통 · 발신 도메인 {doms}")
