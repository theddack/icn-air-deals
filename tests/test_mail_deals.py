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

    def test_ad_mail_with_discount_only_is_accepted(self):
        # 2026-10-27: 판매 기간·도착지 없이 할인율만 있는 (광고) 홍보 메일이 빠졌다
        body = "이번 주 한정, 해외 호텔 최대 25% 할인 혜택을 확인하세요."
        a = md.mail_article("트립닷컴", "(광고) 이번 주 놓치면 아쉬운 혜택", body, SENT, "<t1>", "t")
        self.assertIsNotNone(a)
        self.assertEqual(a["summary_facts"]["fields"].get("discount"), "최대 25%")
        # (광고) 표시가 없으면 예전처럼 판매 기간이나 도착지·금액이 있어야 한다
        from collections import Counter
        why = Counter()
        self.assertIsNone(md.mail_article("트립닷컴", "이번 주 놓치면 아쉬운 혜택", body, SENT, "<t2>", "t", why))
        self.assertEqual(why["not_sale"], 1)

    def test_stages_counted_per_sender(self):
        from unittest import mock
        rows = [{"from": "a", "message_id": "<1>", "uid": b"1", "subject": "(광고) 혜택", "date": SENT, "auth": "ok"},
                {"from": "b", "message_id": "<2>", "uid": b"2", "subject": "회원가입을 환영합니다", "date": SENT, "auth": "ok"}]
        senders = {"a": ("트립닷컴", "trip.com", "domain"), "b": ("제주항공", "jejuair.net", "domain")}
        with mock.patch.object(md.gm, "recent_headers", return_value=(None, rows)), \
             mock.patch.object(md.gm, "airline_of", side_effect=lambda f: senders[f]), \
             mock.patch.object(md.gm, "authenticated", return_value=True), \
             mock.patch.object(md.gm, "message_text", return_value="해외 호텔 최대 25% 할인"):
            out, why = md.collect(None, "t")
        self.assertEqual(len(out), 1)
        self.assertEqual((why["accepted:트립닷컴"], why["transactional:제주항공"], why["accepted"], why["checked"]), (1, 1, 1, 2))

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

    def test_platform_flight_mail_goes_to_flights_with_sender_as_owner(self):
        # 2026-10-26: 낱말 사이 폭 없는 문자 때문에 노선을 못 읽고, 플랫폼 메일이라 숙박 '브랜드 미확인'으로 들어갔다
        subject = "인천​발 오사카​행 이동하는 항공편, 224,867원부터 시작합니다."
        a = md.mail_article("카약", subject, "인천발 오사카행 항공편 224,867원부터", SENT, "<k@kayak.com>", "t")
        self.assertNotIn("​", a["title"])
        d = build_deals([a], date(2026, 10, 21))[0]
        self.assertEqual((d["section"], d["airline"], d["from_icn"]), ("flight", "카약", "yes"))
        self.assertEqual(d["routes"], [{"origin": "인천(ICN)", "destination": "오사카(KIX)"}])
        # 예전에 저장된(폭 없는 문자가 남은) 메일 기사도 화면을 만들 때 다시 정한다
        old = {**a, "title": "카약 " + subject, "category_hint": "hotel"}
        self.assertEqual(enrich(old)["airline"], "h-kayak")

    def test_platform_event_mail_stays_hotel(self):
        self.assertEqual(md.hints("아고다", "주말 호텔 최대 30% 할인"), ("hotel", "h-agoda"))
        self.assertEqual(md.hints("제주항공", "가을 특가 오픈")[0], "flight")

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
