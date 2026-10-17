"""제목은 2026-04 ~ 10 Google 뉴스 RSS에 실제로 올라온 기사에서 가져왔다."""

import unittest
from datetime import date

from collector import extract as x
from collector.extract import attribute_hotel, category_of, extract_discount, is_hotel_sale, route_of


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

    def test_partner_is_not_an_airline(self):
        self.assertEqual(x.detect_airline("클룩·이스타항공, 일본 항공·호텔 특가"), "eastarjet")


class TestMultiAirline(unittest.TestCase):
    """제목에 항공사가 둘 이상 나오는 실제 기사 (2026-07 ~ 10)."""

    def owner(self, title):
        return x.attribute_airline(title)[0]

    def test_two_airlines_one_sale_is_unclassified(self):
        self.assertIsNone(self.owner("90% 이상 할인… 이스타·에어프레미아, 연중 최대 프로모션 시작"))

    def test_roundup_with_two_sales_is_unclassified(self):
        self.assertIsNone(self.owner("10월 항공권 할인전…트리니티 지방 출발 쿠폰·아시아나 결제 할인"))

    def test_sale_belongs_to_preceding_airline(self):
        self.assertEqual(self.owner("트리니티항공, 구마모토 노선 최대 15% 할인... 제주항공, 정비 인재 양성 외[시경Today-항공]"), "trinity")
        self.assertEqual(self.owner("에어서울, '임박 특가' 프로모션→비엣젯항공, '亞대표 항공사' 선정"), "airseoul")
        self.assertEqual(self.owner("비엣젯, 신규취항 기념 특가 항공권→터키항공, 이스탄불서 세계 안전운항 컨퍼런스"), "vietjet")

    def test_wrong_airline_is_never_confirmed(self):
        # 특가는 KLM 것인데 예전 규칙은 먼저 나온 에어캐나다로 분류했다
        self.assertNotEqual(self.owner("[플라이H!] 장거리 여객 공략..에어캐나다 미국 입국 간소화·KLM 107주년 특가"), "aircanada")

    def test_mentioned_list(self):
        self.assertEqual(x.attribute_airline("90% 이상 할인… 이스타·에어프레미아, 연중 최대 프로모션 시작")[1],
                         ["eastarjet", "airpremia"])

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


class TestNotFare(unittest.TestCase):
    """2026-10-18 검토에서 항공권 행사로 잘못 들어온 제목. 할인 대상이 숙박·수하물이다."""

    def test_partner_hotel_discount_is_not_fare(self):
        for t in ["대한항공-아웃리거, 하와이·태국 최대 35% 할인..태양의 서커스도 혜택",
                  "아웃리거X대한항공, 하와이·태국 숙박 최대 35% 할인 프로모션",
                  "아웃리거 리조트 프로모션, 대한항공 항공권 구매하면 하와이·태국 호텔 6곳 최대 35% 할인"]:
            self.assertFalse(x.is_sale_article(t), t)

    def test_baggage_discount_is_not_fare(self):
        for t in ["진에어, 韓·日·대만 신규 고객 잡는다…수하물 할인·항공권 경품 제공",
                  "진에어, 한·일·대만 신규 회원에 수하물 3만원 할인… 왕복 항공권 추첨도"]:
            self.assertFalse(x.is_sale_article(t), t)

    def test_fare_discount_with_hotel_word_stays_fare(self):
        self.assertTrue(x.is_sale_article("진에어, 호텔 결합 항공권 최대 10% 할인"))
        self.assertTrue(x.is_sale_article("에어부산, 연말 국제선 특가 프로모션… 편도 7만5900원부터"))


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

    def test_mere_mention_is_not_origin(self):
        self.assertEqual(x.icn_flag("인천공항 라운지 이용권 할인 이벤트"), "unknown")
        self.assertEqual(x.icn_flag("인천국제공항공사, 면세 할인"), "unknown")
        self.assertEqual(x.icn_flag("LA~인천 노선 특가"), "unknown")

    def test_origin_forms(self):
        self.assertEqual(x.icn_flag("에어부산, 일본·중국·동남아 국제선 특가행사…부산과 인천출발 대상"), "yes")
        self.assertEqual(x.icn_flag("티웨이항공, 인천-자카르타 “편도 총액 239,200원부터”"), "yes")
        self.assertEqual(x.icn_flag("인천발 다낭 노선 특가"), "yes")

    def test_inbound_and_regional_departures_are_not_icn(self):
        # 2026-10-18 검토: 해외 출발·한국행, 지역 공항 출발 행사가 인천 출발 탭에 남아 있었다
        for t in ["에어프레미아, 하와이~한국 노선도 할인… 19일까지 최대 20% 혜택",
                  "에어프레미아, 미주출발 항공권 최대 20% 프로모션",
                  "에어프레미아, 추석맞이 한국행 항공권 최대 80% 할인",
                  "아시아나, 미주~인천행 비즈니스석 7% 할인 특가",
                  "트리니티항공, 지역 공항 출발 항공권 할인…23일까지 ‘우리 동네 할인’ 진행",
                  "트리니티항공, 지방 공항 출발 노선 대상 ‘우리 동네 할인’ 프로모션 실시"]:
            self.assertEqual(x.icn_flag(t), "no", t)
        self.assertEqual(x.icn_flag("비엣젯항공, 국제선 확대 기념 특가 프로모션…한국~베트남 편도 12만9천원부터"), "unknown")
        self.assertEqual(x.icn_flag("에어프레미아, 미주 노선 최대 25% 할인…인천~LA 노선 취항 4주년"), "yes")


class TestTravel(unittest.TestCase):
    def check(self, title, pub, start, end):
        s, e = x.extract_travel(title, D(pub))
        self.assertEqual((s.isoformat() if s else None, e.isoformat() if e else None), (start, end), title)

    def test_until_date_boarding(self):
        self.check("티웨이항공, 해외 노선 특가 프로모션 실시..12월 31일까지 탑승 가능", "2026-08-20", None, "2026-12-31")

    def test_month_range_departure(self):
        self.check("티웨이항공, 6~8월 출발 항공권 할인 프로모션 진행", "2026-06-19", "2026-06-01", "2026-08-31")

    def test_next_year_months(self):
        self.check("트리니티항공, 내년 1~3월 국제선 항공권 최대 24% 할인", "2026-10-10", "2027-01-01", "2027-03-31")

    def test_next_year_quarter(self):
        self.check("트리니티항공, 내년 1분기 국제선 최대 24% 할인", "2026-10-13", "2027-01-01", "2027-03-31")

    def test_single_month(self):
        self.check("OO항공, 12월 출발 일본 노선 특가", "2026-10-10", "2026-12-01", "2026-12-31")

    def test_sale_date_is_not_travel(self):
        self.check("에어부산, 연말 국제선 특가 프로모션…14일부터 20일까지", "2026-10-10", None, None)
        self.check("진에어, 13일부터 4일간 ‘진마켓’ 운영…최대 96% 할인", "2026-07-08", None, None)


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


class TestRoute(unittest.TestCase):
    def test_domestic_pair_ignores_airline_names(self):
        self.assertEqual(route_of("제주항공, 김포~제주 노선 특가"), ("domestic", "김포~제주"))
        self.assertEqual(route_of("제주항공, 부산~마닐라 12월 17일 취항...최대 50% 할인"), (None, None))

    def test_domestic_words(self):
        self.assertEqual(route_of("진에어, 국내선 항공권 최대 30% 할인")[0], "domestic")
        self.assertEqual(route_of("에어부산, 제주행 항공권 특가")[0], "domestic")

    def test_international_wins_when_both(self):
        self.assertEqual(route_of("진에어, 추석 항공권 최대 15% 할인⋯국제선 43개 노선·국내 역귀성 대상")[0], "international")
        self.assertEqual(route_of("트리니티항공, 인천~구마모토 최대 15% 할인")[0], "international")


class TestHotel(unittest.TestCase):
    def test_hotel_sale(self):
        self.assertTrue(is_hotel_sale("여기어때, 가평 숙소 대상 최대 3만원 할인 쿠폰 제공"))
        self.assertTrue(is_hotel_sale("파라다이스, 21일까지 하반기 슈퍼위크…객실·스파 할인 혜택"))

    def test_not_hotel_sale(self):
        # 숙박 맥락 없음 / 할인 없음 / 숙박 아닌 할인
        self.assertFalse(is_hotel_sale("소노인터내셔널, 비발디파크 파크골프 최대 34% 할인"))
        self.assertFalse(is_hotel_sale("롯데호텔앤리조트, 두짓호텔앤리조트와 멤버십 협력"))
        self.assertFalse(is_hotel_sale("“폴루아-벨루오와 가을 소풍”… 롯데호텔 뷔페 30% 할인"))

    def test_campaign_owns_article(self):
        self.assertEqual(attribute_hotel("놀·여기어때, 숙박세일 페스타 참여…비수도권·섬 지역 숙소 할인")[0], "h-stayfesta")
        self.assertIsNone(attribute_hotel("여기어때·아고다, 호텔 특가 경쟁")[0])

    def test_flight_wins_over_hotel(self):
        self.assertEqual(category_of("트리니티항공, 국제선 60개 노선 최대 22% 할인"), "flight")
        # 2026-10-18: 항공사가 나와도 할인 대상이 제휴 호텔 숙박이면 호텔 행사다
        self.assertEqual(category_of("에어서울, 인스파이어와 맞손…탑승객 투숙하면 최대 15% 할인"), "hotel")
        self.assertEqual(category_of("여기어때, 가평 숙소 대상 최대 3만원 할인 쿠폰 제공"), "hotel")
        self.assertIsNone(category_of("롯데호텔 침구 백화점서 산다"))

    def test_amount_discount(self):
        self.assertEqual(extract_discount("강원 숙박상품 최대 7만원 할인…22일부터"), "최대 7만원 할인")
        self.assertEqual(extract_discount("여기어때, 가평 전 숙박시설 ‘최대 3만 원’ 선착순 할인"), "최대 3만원 할인")


class TestAirports(unittest.TestCase):
    def test_pair_and_codes(self):
        self.assertEqual(x.airports("트리니티항공, 인천~구마모토 노선 최대 15% 할인"), ("인천(ICN)", "구마모토(KMJ)"))
        self.assertEqual(x.airports("제주항공, 부산~마닐라 12월 17일 취항...최대 50% 할인"), ("부산(PUS)", "마닐라(MNL)"))

    def test_airline_name_is_not_a_place(self):
        # '세부퍼시픽'의 세부, '제주항공'의 제주는 노선이 아니다
        self.assertEqual(x.airports("세부퍼시픽, 세부행 특가"), (None, "세부(CEB)"))
        self.assertEqual(x.airports("제주항공, 최대 50% 할인"), (None, None))

    def test_city_without_single_airport_has_no_code(self):
        self.assertEqual(x.airports("진에어, 인천~도쿄 특가"), ("인천(ICN)", "도쿄"))

    def test_domestic_pair_text(self):
        self.assertEqual(x.route_of("제주항공, 김포~제주 노선 특가"), ("domestic", "김포~제주"))
        self.assertEqual(x.route_of("에어프레미아, 하와이~한국 왕복 특가")[0], None)


class TestHotelFields(unittest.TestCase):
    def test_regions(self):
        self.assertEqual(x.hotel_regions("전남광주통합특별시, 숙박세일 페스타 가을편…최대 7만 원 할인"), ["전남광주"])
        self.assertEqual(x.hotel_regions("마이리얼트립, 日 규슈 사가현 숙소·렌터카 할인"), ["규슈", "사가현"])

    def test_conditions(self):
        self.assertEqual(x.hotel_conditions("강원도 22일부터 ‘숙박세일페스타’…연박시 최대 7만원 할인"), ["연박"])
        self.assertEqual(x.hotel_conditions("여기어때, 가평 숙소 대상 최대 3만원 할인 쿠폰 제공 선착순"), ["쿠폰", "선착순"])


class TestFareSaleRule(unittest.TestCase):
    """2026-10-15 보완 규칙. 같은 날 탈락 기사 45건을 사람이 읽고 나눈 결과에서 뽑은 제목들."""

    def test_fare_promotions_now_collected(self):
        for t in ["트리니티항공, 10월 '우리 동네 할인' 프로모션 진행",
                  "트리니티항공, 지역공항 출발편 할인…부산·대구·청주 대상",
                  "트리니티항공, 日구마모토 공항과 공동 프로모션",
                  "에어프레미아, 10~17일 할인이벤트 ‘프로미스’ 실행",
                  "KLM, ‘107번째 델프트 미니어처 하우스’ 공개→선착순 할인 프로모션"]:
            self.assertTrue(x.is_sale_article(t), t)

    def test_ancillary_offers_stay_out(self):
        for t in ["제주항공, 'J멤버십' 최대 5만원 할인…수하물·반려동물 운송비 절감",
                  "진에어, 한·일·대만 신규 회원에 수하물팩 3만원 할인쿠폰 지급",
                  "에이비스, 대한항공 스카이패스 회원 대상 제휴 마일리지 적립 프로모션 실시",
                  "파라타항공, 문어 들기름막국수 선봬…비빔밥 할인 행사도",
                  "싱가포르항공, 더현대 서울 팝업스토어 오픈…오감 체험·마일리지 프로모션 진행"]:
            self.assertFalse(x.is_sale_article(t), t)

    def test_leading_slogan_is_not_event_name(self):
        self.assertEqual(x.extract_event_name("“지방공항 출발시 할인” 트리니티항공, 이달23일까지 '우리동네 프로모션'"), "우리동네 프로모션")
        self.assertEqual(x.normalize_event_name("우리동네 프로모션"), x.normalize_event_name("우리 동네 할인"))
