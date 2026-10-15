"""제목은 2026-04 ~ 10 Google 뉴스 RSS에 실제로 올라온 기사에서 가져왔다."""

import unittest
from datetime import date

from collector import extract as x


def D(s):
    return date.fromisoformat(s)


class TestDates(unittest.TestCase):
    def check(self, title, pub, start, end):
        s, e = x.extract_dates(title, D(pub))
        self.assertEqual((s.isoformat() if s else None, e.isoformat() if e else None), (start, end), title)

    def test_start_day_only(self):
        self.check("이스타항공, 13일부터 연중 최대 할인 프로모션", "2026-07-06", "2026-07-13", None)

    def test_start_with_month(self):
        self.check("연중 최대 항공권 할인, 진에어 `진마켓` 7월13일부터 열린다", "2026-07-08", "2026-07-13", None)

    def test_start_and_duration(self):
        self.check("진에어, 13일부터 4일간 ‘진마켓’ 운영…최대 96% 할인", "2026-07-08", "2026-07-13", "2026-07-16")

    def test_korean_duration(self):
        self.check("진에어, 최대 96% 할인 ‘진마켓’ 13일부터 나흘간 진행", "2026-07-08", "2026-07-13", "2026-07-16")

    def test_start_keyword_sijak(self):
        self.check("에어서울 '사이다 특가' 13일 시작...운임 500원 수준까지", "2026-07-10", "2026-07-13", None)

    def test_oneun(self):
        self.check("에어프레미아, 오는 6일부터 최대 90% 할인 '프로미스' 프로모션", "2026-07-02", "2026-07-06", None)

    def test_today(self):
        self.check("제주항공, 연중 최대 할인 ‘찜(JJIM) 특가’ 실시…오늘부터 판매", "2026-07-07", "2026-07-07", None)

    def test_tomorrow_with_duration(self):
        self.check("에어부산, 내일부터 7일간 국내선 할인 판매", "2026-08-10", "2026-08-11", "2026-08-17")

    def test_range_buteo_kkaji(self):
        self.check("에어부산, 연말 국제선 특가 프로모션…14일부터 20일까지", "2026-10-10", "2026-10-14", "2026-10-20")

    def test_end_only(self):
        self.check("티웨이항공, 13일까지 국제선 53개 노선 특가 프로모션 진행", "2026-05-01", None, "2026-05-13")

    def test_end_with_month(self):
        self.check("티웨이항공, 여름휴가 시즌 국제선 항공권 할인…6월30일까지", "2026-06-19", None, "2026-06-30")

    def test_end_with_month_and_sale_word(self):
        self.check("핀에어, 유럽 25개 노선 최대 30% 할인⋯9월25일까지 판매", "2026-09-01", None, "2026-09-25")

    def test_travel_period_is_not_sale_end(self):
        # 31일까지 판매 + 12월 31일까지 탑승 → 판매 마감은 31일(8월)
        self.check("티웨이항공, 해외 노선 특가 프로모션 실시..12월 31일까지 탑승 가능", "2026-08-20", None, None)
        self.check("티웨이항공, 31일까지 해외 항공권 특가 프로모션", "2026-08-20", None, "2026-08-31")

    def test_route_launch_date_ignored(self):
        self.check("다음 달 7일부터 일본 고베 직항으로 간다…진에어, 15% 할인", "2026-07-21", None, None)
        self.check("티웨이항공, 인천-자카르타 “편도 총액 239,200원부터”… 정기편 4월 29일 첫 취항", "2026-04-21", None, None)

    def test_duration_word_not_a_date(self):
        self.check("비엣젯항공, 3일간 베트남 노선 특가 프로모션 실시", "2026-09-01", None, None)

    def test_end_rolls_to_next_month(self):
        self.check("OO항공, 5일까지 특가", "2026-09-28", None, "2026-10-05")

    def test_end_in_january_from_december(self):
        self.check("OO항공, 1월 10일까지 특가", "2026-12-20", None, "2027-01-10")

    def test_short_range(self):
        self.check("OO항공 13~16일 특가", "2026-07-08", "2026-07-13", "2026-07-16")

    def test_no_date(self):
        self.check("비즈니스석도 할인…티웨이항공, 국제선 얼리버드 특가 오픈", "2026-07-10", None, None)


class TestAirline(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(x.detect_airline("에어부산, 내일부터 7일간 국내선 할인 판매"), "airbusan")

    def test_first_mention_wins(self):
        self.assertEqual(x.detect_airline("클룩·이스타항공, 일본 항공·호텔 특가"), "eastarjet")
        self.assertEqual(x.detect_airline("90% 이상 할인… 이스타·에어프레미아, 연중 최대 프로모션 시작"), "eastarjet")

    def test_longer_alias(self):
        self.assertEqual(x.detect_airline("타이에어아시아 특가"), "airasia")
        self.assertEqual(x.detect_airline("아시아나항공 프로모션"), "asiana")

    def test_ascii_boundary(self):
        self.assertIsNone(x.detect_airline("BANANA 할인"))
        self.assertEqual(x.detect_airline("ANA 할인 운임"), "ana")


class TestFilters(unittest.TestCase):
    def test_quiz_noise(self):
        self.assertFalse(x.is_sale_article("[종합]\"제주항공,팬마음 투표\" 등 7월 8일 캐시워크 돈버는퀴즈 전체 문제+정답!"))

    def test_sale(self):
        self.assertTrue(x.is_sale_article("제주항공 찜 특가 시작…일본 6만8900원부터"))

    def test_not_sale(self):
        self.assertFalse(x.is_sale_article("대한항공, 일등석 기내식 사전 주문 서비스 확대"))

    def test_weak_word_needs_ticket_context(self):
        self.assertFalse(x.is_sale_article("파라타항공, 문어 들기름막국수 선봬…비빔밥 할인 행사도"))
        self.assertFalse(x.is_sale_article("싱가포르항공, 더현대 서울 팝업스토어 오픈…오감 체험·마일리지 프로모션 진행"))
        self.assertTrue(x.is_sale_article("트리니티항공, 국제선 60개 노선 최대 22% 할인"))
        self.assertTrue(x.is_sale_article("에어프레미아, 하와이~한국 노선도 할인… 19일까지 최대 20% 혜택"))


class TestRenamedAirline(unittest.TestCase):
    def test_tway_is_trinity(self):
        self.assertEqual(x.detect_airline("티웨이항공, 13일까지 국제선 특가"), "trinity")
        self.assertEqual(x.detect_airline("트리니티항공, 지역 공항 출발 항공권 할인"), "trinity")


class TestDiscount(unittest.TestCase):
    def test_max_percent(self):
        self.assertEqual(x.extract_discount("진에어, 하반기 '진마켓' 오픈...국제선 최대 96% 특가"), "최대 96%")

    def test_price(self):
        self.assertEqual(x.extract_discount("제주항공 찜 특가 시작…일본 6만8900원부터"), "6만8900원부터")

    def test_percent(self):
        self.assertEqual(x.extract_discount("진에어, 15% 할인"), "15% 할인")


class TestIcn(unittest.TestCase):
    def test_yes(self):
        self.assertEqual(x.icn_flag("티웨이항공, 28일까지 인천~구마모토 특별 할인 프로모션"), "yes")

    def test_no_domestic(self):
        self.assertEqual(x.icn_flag("에어부산, 11일부터 국내선 4개 노선 특가 프로모션 진행"), "no")

    def test_no_other_origin(self):
        self.assertEqual(x.icn_flag("부산-후쿠오카 노선 특가"), "no")

    def test_airline_name_is_not_origin(self):
        self.assertEqual(x.icn_flag("제주항공 찜 특가 시작"), "unknown")


class TestEventName(unittest.TestCase):
    def test_names(self):
        self.assertEqual(x.extract_event_name("진에어, 13일부터 4일간 ‘진마켓’ 운영"), "진마켓")
        self.assertEqual(x.extract_event_name("에어서울 '사이다 특가' 13일 시작"), "사이다 특가")

    def test_skip_price_quote(self):
        self.assertIsNone(x.extract_event_name("인천-자카르타 “편도 총액 239,200원부터”"))

    def test_normalize(self):
        self.assertEqual(x.normalize_event_name("2026 하반기 진마켓"), x.normalize_event_name("진마켓"))
        self.assertEqual(x.normalize_event_name("찜(JJIM) 특가"), x.normalize_event_name("찜 특가"))


if __name__ == "__main__":
    unittest.main()
