"""항공사 뉴스레터 → 행사 기사. 메일 제목·본문은 형식만 흉내 낸 예시다(실제 수신 메일 아님)."""

import json
import unittest
from datetime import date, datetime

from collector import mail_deals as md
from collector.main import build_deals, enrich
from collector.status import KST

SENT = datetime(2026, 10, 19, 9, 0, tzinfo=KST)
BODY = ("홍길동님, 가을 특가가 시작됩니다. 판매기간: 10월 20일~10월 26일. 탑승기간: 12월 1일~2월 28일. "
        "인천-오사카 편도 총액 59,000원부터, 최대 30% 할인. 쿠폰코드 AB12CD34 입력 시 추가 할인. "
        "https://track.example/click?u=abc123 회원번호 12345678")


class TestCleanSubject(unittest.TestCase):
    def test_private_bits_removed(self):
        s = md.clean_subject("(광고) 홍길동님, 회원번호 12345678 전용 쿠폰 AB12CD34 · 오사카 특가 https://x.example/a")
        for bad in ("광고", "홍길동", "12345678", "AB12CD34", "http"):
            self.assertNotIn(bad, s)
        self.assertIn("오사카 특가", s)


class TestMailArticle(unittest.TestCase):
    def test_sale_mail_becomes_article_without_body_or_links(self):
        a = md.mail_article("제주항공", "(광고) 홍길동님 가을 특가 오픈", BODY, SENT, "<abc@mail.jejuair.net>", "t")
        self.assertEqual(a["source"], "mail")
        self.assertTrue(a["title"].startswith("제주항공"))
        f = a["summary_facts"]["fields"]
        self.assertEqual((f["sale_start"], f["sale_end"]), ("2026-10-20", "2026-10-26"))
        self.assertEqual((f["travel_start"], f["travel_end"]), ("2026-12-01", "2027-02-28"))
        # 공개 저장소에 올라가는 값에 본문 문장·쿠폰·추적 링크·이름·회원번호가 없어야 한다
        dumped = json.dumps(a, ensure_ascii=False)
        for bad in ("홍길동", "AB12CD34", "track.example", "12345678", "쿠폰코드", "가을 특가가 시작됩니다"):
            self.assertNotIn(bad, dumped)
        self.assertTrue(a["url"].startswith("https://www.jejuair.net/"))

    def test_non_sale_or_unknown_airline_mail_is_skipped(self):
        self.assertIsNone(md.mail_article("제주항공", "회원가입을 환영합니다", "가입해 주셔서 감사합니다.", SENT, "<a>", "t"))
        self.assertIsNone(md.mail_article("제주항공", "가을 특가 오픈", "자세한 내용은 앱에서 확인하세요.", SENT, "<b>", "t"))
        self.assertIsNone(md.mail_article("춘추항공", "가을 특가 오픈", BODY, SENT, "<c>", "t"))  # airlines.py에 없음

    def test_filter_stages_are_counted(self):
        from collections import Counter
        why = Counter()
        md.mail_article("춘추항공", "가을 특가", BODY, SENT, "<1>", "t", why)
        md.mail_article("제주항공", "회원가입을 환영합니다", BODY, SENT, "<2>", "t", why)
        md.mail_article("제주항공", "가을 특가 오픈", "앱에서 확인하세요.", SENT, "<3>", "t", why)
        self.assertEqual(dict(why), {"not_listed": 1, "transactional": 1, "no_facts": 1})

    def test_plain_subject_accepted_by_body_facts(self):
        # 제목에 특가 표현이 없어도 본문에 판매 기간, 또는 금액+도착지가 있으면 받는다 (2026-10-25)
        a = md.mail_article("제주항공", "이번 주 소식", "판매기간: 10월 20일~10월 26일. 일본 노선 안내.", SENT, "<p1>", "t")
        self.assertEqual(a["summary_facts"]["fields"]["sale_end"], "2026-10-26")
        b = md.mail_article("제주항공", "가을 여행 떠나세요", "인천-오사카 편도 총액 59,000원부터", SENT, "<p2>", "t")
        self.assertEqual(b["summary_facts"]["fields"]["destination"], "오사카(KIX)")
        self.assertEqual(build_deals([b], date(2026, 10, 21))[0]["verification"], "official")

    def test_plain_subject_without_sale_or_price_route_is_skipped(self):
        from collections import Counter
        why = Counter()
        self.assertIsNone(md.mail_article("제주항공", "가을 소식", "탑승기간: 12월 1일~2월 28일. 최대 30% 할인", SENT, "<p3>", "t", why))
        self.assertEqual(dict(why), {"not_sale": 1})

    def test_transactional_mails_are_skipped(self):
        for subject, body in [("예약 확인 안내", "인천-오사카 편도 59,000원. 판매기간 10월 20일~26일"),
                              ("가을 특가 오픈", "이메일 인증 번호는 123456 입니다. 판매기간 10월 20일~26일"),
                              ("Your e-ticket receipt", "ICN-NRT 120,000원")]:
            self.assertIsNone(md.mail_article("제주항공", subject, body, SENT, "<t>", "t"), subject)

    def test_deal_from_mail_is_official(self):
        a = md.mail_article("제주항공", "가을 특가 오픈", BODY, SENT, "<abc@mail.jejuair.net>", "t")
        deals = build_deals([a], date(2026, 10, 21))
        self.assertEqual(len(deals), 1)
        d = deals[0]
        self.assertEqual(d["verification"], "official")
        self.assertEqual((d["sale_start"], d["sale_end"]), ("2026-10-20", "2026-10-26"))
        self.assertEqual(d["evidence"]["sale"]["title"], "제주항공 메일 본문")

    def test_news_deal_stays_news(self):
        news = {"title": "제주항공, 가을 특가 오픈…20일부터", "outlet": "o", "url": "u", "published": "2026-10-19", "first_seen": "t"}
        self.assertEqual(build_deals([news], date(2026, 10, 21))[0]["verification"], "news")


class TestMerge(unittest.TestCase):
    def test_dedupe_and_retention(self):
        a = {"mail_id": "a", "published": "2026-10-19"}
        old = {"mail_id": "o", "published": "2026-08-01"}
        kept, added = md.merge([a, old], [{"mail_id": "a", "published": "2026-10-19"}, {"mail_id": "b", "published": "2026-10-20"}],
                               date(2026, 10, 25))
        self.assertEqual(([k["mail_id"] for k in kept], added), (["b", "a"], 1))


if __name__ == "__main__":
    unittest.main()


class TestPlatformEvents(unittest.TestCase):
    """2026-10-25: 스카이스캐너·카약 이벤트 (뉴스와 메일)."""

    def test_news_titles(self):
        from collector import extract as x
        self.assertEqual(x.category_of("스카이스캐너, 블랙프라이데이 항공권 최대 30% 할인 코드"), "hotel")
        self.assertEqual(x.attribute_hotel("카약(KAYAK), 연말 해외여행 특가 모음")[0], "h-kayak")
        self.assertIsNone(x.category_of("한강 카약 체험 할인 이벤트"))           # 레저 카약은 아니다
        self.assertEqual(x.category_of("제주항공, 스카이스캐너와 공동 특가"), "flight")  # 항공사 특가는 그대로 항공권

    def test_platform_mail_is_platform_event(self):
        from collector.sources.gmail_imap import airline_of
        self.assertEqual(airline_of("Skyscanner <deals@email.skyscanner.net>")[:3:2], ("스카이스캐너", "domain"))
        a = md.mail_article("스카이스캐너", "이번 주 특가 여행지", "인천-오사카 왕복 129,000원부터. 판매기간 10월 20일~10월 31일",
                            SENT, "<sk1>", "t")
        self.assertEqual((a["category_hint"], a["url"].startswith("https://www.skyscanner.co.kr/")), ("hotel", True))
        d = build_deals([a], date(2026, 10, 21))[0]
        self.assertEqual((d["section"], d["airline_id"], d["verification"]), ("hotel", "h-skyscanner", "official"))
