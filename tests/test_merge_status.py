import unittest
from datetime import date

from collector.main import build_deals, enrich
from collector.merge import cluster_articles
from collector.status import display_status, should_keep, status


def art(title, pub, url=None):
    return enrich({"title": title, "outlet": "test", "url": url or title, "published": pub, "first_seen": pub})


class TestMerge(unittest.TestCase):
    def test_jinmarket_articles_become_one_deal(self):
        # 2026-07 실제 기사 제목: 이름만 있는 것, 날짜만 있는 것, 둘 다 있는 것이 섞여 있다
        arts = [
            art("진에어, 하반기 '진마켓' 티저 오픈…항공권 최대 96% 할인", "2026-07-08"),
            art("진에어, 13일부터 4일간 ‘진마켓’ 운영…최대 96% 할인", "2026-07-08"),
            art("진에어, 연중 최대 특가 ‘2026 하반기 진마켓’ 오픈", "2026-07-13"),
            art("진에어, 16일까지 '하반기 진마켓' 진행…최대 96% 운임 할인", "2026-07-13"),
            art("진에어, 하반기 '진마켓' 오픈...국제선 최대 96% 특가", "2026-07-13"),
        ]
        deals = cluster_articles(arts)
        self.assertEqual(len(deals), 1)
        d = deals[0]
        self.assertEqual((d["sale_start"], d["sale_end"]), ("2026-07-13", "2026-07-16"))
        self.assertEqual(d["discount"], "최대 96%")
        self.assertEqual(len(d["articles"]), 5)

    def test_dated_article_without_name_joins_named_deal(self):
        arts = [
            art("이스타항공, 연중 최대 특가 ‘슈퍼 스타 페스타’ 13일 시작…국제선 최대 99% 할인", "2026-07-06"),
            art("이스타항공, 13일부터 연중 최대 할인 프로모션", "2026-07-06"),
        ]
        self.assertEqual(len(cluster_articles(arts)), 1)

    def test_different_airlines_never_merge(self):
        arts = [
            art("이스타항공, 13일부터 연중 최대 할인 프로모션", "2026-07-06"),
            art("진에어, 13일부터 4일간 ‘진마켓’ 운영", "2026-07-08"),
        ]
        self.assertEqual(len(cluster_articles(arts)), 2)

    def test_domestic_and_international_never_merge(self):
        # 같은 날 같은 항공사여도 국내선 행사와 국제선 행사는 따로 둔다 (이틀 내 보도 규칙보다 우선)
        arts = [
            art("진에어, 국내선 항공권 최대 30% 할인", "2026-09-22"),
            art("진에어, 국제선 항공권 최대 15% 할인", "2026-09-22"),
        ]
        deals = sorted(cluster_articles(arts), key=lambda d: d["section"])
        self.assertEqual([d["section"] for d in deals], ["domestic", "flight"])

    def test_travel_disagreement_is_not_resolved(self):
        # 같은 행사인데 기사마다 탑승 기간이 다르면 한쪽을 고르지 않는다
        arts = [
            art("진에어, '진마켓' 오픈…내년 1~3월 탑승 최대 96% 할인", "2026-07-08"),
            art("진에어, '진마켓' 오픈…내년 2~3월 탑승 최대 96% 할인", "2026-07-08"),
        ]
        d = cluster_articles(arts)[0]
        self.assertEqual((d["travel_start"], d["travel_end"], d["conflicts"]), (None, None, ["travel"]))

    def test_evidence_points_to_article_with_value(self):
        arts = [
            art("진에어, '진마켓' 티저 오픈", "2026-07-08", url="a"),
            art("진에어, 16일까지 '진마켓' 진행…최대 96% 운임 할인", "2026-07-13", url="b"),
        ]
        d = cluster_articles(arts)[0]
        self.assertEqual((d["evidence"]["sale"]["url"], d["evidence"]["discount"]["url"]), ("b", "b"))
        self.assertNotIn("travel", d["evidence"])

    def test_agency_link_only_when_named_in_title(self):
        d = cluster_articles([art("하나투어, 진에어 일본 노선 항공권 최대 30% 할인", "2026-10-02")])[0]
        self.assertEqual(d["agencies"], [{"name": "하나투어", "url": "https://www.hanatour.com/"}])
        d = cluster_articles([art("진에어, 일본 노선 항공권 최대 30% 할인", "2026-10-02")])[0]
        self.assertEqual(d["agencies"], [])

    def test_hotel_deal_has_no_airport(self):
        d = cluster_articles([art("여기어때, 가평 숙소 대상 최대 3만원 할인 쿠폰 제공", "2026-10-02")])[0]
        self.assertEqual((d["section"], d["from_icn"], d["airline"]), ("hotel", None, "여기어때"))

    def test_elandpark_saipan_articles_become_one_deal(self):
        # 2026-10-16 실제 기사: 브랜드 미확인으로 처리돼 같은 행사가 7건으로 갈라졌다
        arts = [
            art("이랜드파크, 사이판 호텔·리조트 3곳 '1+1' 프로모션", "2026-10-16"),
            art("\"액티비티 혜택 두배로\"…이랜드파크 사이판 호텔·리조트, '1+1 프로모션' 전개", "2026-10-16"),
            art("이랜드파크, 사이판 호텔·리조트 3곳 ‘버킷리스트 투어 바우처 1+1’ 프로모션 진행", "2026-10-16"),
        ]
        deals = cluster_articles(arts)
        self.assertEqual(len(deals), 1)
        self.assertEqual((deals[0]["section"], deals[0]["scope"]), ("hotel", "overseas"))

    def test_unknown_brand_hotels_merge_only_by_event_name(self):
        # 2026-10-15·17 실제 기사: 브랜드는 없지만 같은 '가을 페이백' 행사
        arts = [
            art("괌 주요 리조트 동계 시즌 요금 조정 및 프로모션 '괌 가을 페이백’ 전개", "2026-10-15"),
            art("괌 5개 호텔, '가을 페이백' 프로모션…최대 79% 할인", "2026-10-17"),
            art("겨울방학·연말 수요 겨냥…괌 호텔 5곳 공동 프로모션 진행", "2026-10-15"),  # 이름 없음: 따로 둔다
        ]
        deals = sorted(cluster_articles(arts), key=lambda d: len(d["articles"]))
        self.assertEqual([len(d["articles"]) for d in deals], [1, 2])
        self.assertTrue(all(d["airline"] == "브랜드 미확인" for d in deals))

    def test_different_events_same_airline(self):
        arts = [
            art("에어부산, 내일부터 연중 최대 규모 동계 항공권 할인", "2026-07-21"),
            art("에어부산, 연말 국제선 특가 프로모션…14일부터 20일까지", "2026-10-10"),
        ]
        self.assertEqual(len(cluster_articles(arts)), 2)

    def test_undated_articles_merge_by_discount_and_words(self):
        # 2026-10 실제 기사: 날짜·따옴표 없이 쓴 기사가 많다
        arts = [
            art("트리니티항공, 해외 노선 ‘얼리버드 프로모션’ 시행…최대 24% 할인", "2026-10-13"),
            art("\"내년 초 여행, 미리 준비해볼까\"…트리니티항공, 국제선 얼리버드 프로모션", "2026-10-13"),
            art("트리니티항공, 국제선 ‘얼리버드’ 프로모션…내년 초 출발 항공권 최대 24% 할인", "2026-10-14"),
            art("새해 여행 얼리버드 잡아라…트리니티항공 국제선 프로모션", "2026-10-14"),
            art("트리니티항공, 내년 1분기 국제선 최대 24% 할인", "2026-10-14"),
        ]
        self.assertEqual(len(cluster_articles(arts)), 1)

    def test_same_discount_but_different_end_stays_apart(self):
        arts = [
            art("트리니티항공, 13일까지 국제선 최대 22% 할인", "2026-10-02"),
            art("트리니티항공, 지역 공항 출발 항공권 할인…23일까지 최대 22% 할인", "2026-10-08"),
        ]
        self.assertEqual(len(cluster_articles(arts)), 2)

    def test_icn_yes_if_any_article_says_so(self):
        arts = [
            art("티웨이항공, 28일까지 인천~구마모토 특별 할인 프로모션", "2026-06-16"),
            art("티웨이항공, 28일까지 구마모토 특가", "2026-06-16"),
        ]
        self.assertEqual(cluster_articles(arts)[0]["from_icn"], "yes")


class TestNotNews(unittest.TestCase):
    def test_shopping_listing_is_not_an_article(self):
        from collector.main import to_article
        raw = {"raw_title": "[본사직영] 켄싱턴리조트 경주, 단, 하루 특가!! - 쿠팡", "outlet": "쿠팡", "url": "u", "published": "2026-10-19"}
        self.assertIsNone(to_article(raw, "2026-10-19T09:00:00+09:00"))


class TestRules20261021(unittest.TestCase):
    # 2026-10-20 수집에 들어온 실제 제목
    def test_several_carriers_named_one(self):
        from collector.extract import attribute_airline
        self.assertIsNone(attribute_airline("KB페이로 국제선 사면 12% 할인…제주항공 등 5개 LCC 대상")[0])

    def test_bank_event_is_not_fare_sale(self):
        from collector.extract import category_of
        self.assertIsNone(category_of("“올리브영 할인에 대한항공 50만원까지”… 신한은행, ‘SOL통장·트래블’ 연계 대규모 고객 이벤트 전격 실시"))

    def test_trend_report_is_not_hotel_sale(self):
        from collector.extract import category_of
        self.assertIsNone(category_of("[현장] 호텔스닷컴 '언팩 27' 발표…부산 여행 검색 50% 늘고 짧은 여행 관심 확대"))
        self.assertEqual(category_of("에어서울, 일본 노선 최대 50% 할인…예약 늘고"), "flight")  # 할인 표현이 있으면 행사

    def test_tech_event_is_not_stay_sale(self):
        from collector.extract import category_of
        self.assertIsNone(category_of("야놀자, 'AI 페스타 2026' 참가…여행·호텔·아파트 AI 기술 총출동"))
        self.assertEqual(category_of("NOL, 가평군과 가을숙소 프로모션...최대 3만원 할인"), "hotel")

    def test_hotel_drink_discount_is_not_stay_sale(self):
        from collector.extract import category_of
        self.assertIsNone(category_of("롯데호텔 '논알코올' 칵테일 7종 출시…연말까지 10% 할인"))


class TestStatus(unittest.TestCase):
    def test_states(self):
        s, e = date(2026, 7, 13), date(2026, 7, 16)
        self.assertEqual(status(s, e, date(2026, 7, 10)), "upcoming")
        self.assertEqual(status(s, e, date(2026, 7, 13)), "live")
        self.assertEqual(status(s, e, date(2026, 7, 16)), "live")
        self.assertEqual(status(s, e, date(2026, 7, 17)), "ended")
        self.assertEqual(status(None, e, date(2026, 7, 1)), "live")
        self.assertEqual(status(s, None, date(2026, 8, 30)), "live")
        self.assertEqual(status(None, None, date(2026, 7, 1)), "undated")

    def test_keep(self):
        d = {"sale_start": "2026-07-13", "sale_end": "2026-07-16", "last_published": "2026-07-13"}
        self.assertTrue(should_keep(d, date(2026, 7, 23)))
        self.assertFalse(should_keep(d, date(2026, 7, 24)))
        open_ended = {"sale_start": "2026-07-07", "sale_end": None, "last_published": "2026-07-08"}
        self.assertTrue(should_keep(open_ended, date(2026, 7, 22)))
        self.assertFalse(should_keep(open_ended, date(2026, 7, 23)))  # 정보가 없으면 14일에 뺀다

    def test_stale_with_facts_kept_30_days(self):
        # 2026-10 에어서울 '임박 특가'(마지막 기사 10/4): 마감일이 없어 10/18에 사라지던 것
        d = {"sale_start": None, "sale_end": None, "last_published": "2026-10-04", "event_name": "임박 특가",
             "discount": "12만원대부터"}
        self.assertEqual(display_status(d, date(2026, 10, 18)), "undated")
        self.assertEqual(display_status(d, date(2026, 10, 19)), "stale")
        self.assertTrue(should_keep(d, date(2026, 11, 3)))
        self.assertFalse(should_keep(d, date(2026, 11, 4)))
        started = {"sale_start": "2026-10-01", "sale_end": None, "last_published": "2026-10-01", "discount": "최대 10%"}
        self.assertEqual(display_status(started, date(2026, 10, 16)), "stale")
        upcoming = {"sale_start": "2026-12-01", "sale_end": None, "last_published": "2026-10-01"}
        self.assertEqual(display_status(upcoming, date(2026, 10, 20)), "upcoming")

    def test_price_range_wording(self):
        from collector.extract import extract_discount
        self.assertEqual(extract_discount("에어서울, 국제선 전 노선 '임박 특가'...다낭 12만원대부터"), "12만원대부터")
        self.assertEqual(extract_discount("에어부산, 편도 7만5900원부터"), "7만5900원부터")



class TestRefilterStored(unittest.TestCase):
    def test_stored_article_that_no_longer_qualifies_is_dropped(self):
        # 2026-10-18: 저장돼 있던 제휴 호텔 할인 기사가 규칙을 고친 뒤에도 항공권 행사로 남던 문제
        stored = [{"title": t, "outlet": "o", "url": t, "published": "2026-10-16", "first_seen": "2026-10-16T00:00:00+09:00"}
                  for t in ("대한항공-아웃리거, 하와이·태국 최대 35% 할인..태양의 서커스도 혜택",
                            "트리니티항공, 국제선 60개 노선 최대 22% 할인")]
        deals = build_deals(stored, date(2026, 10, 18))
        self.assertEqual([d["airline"] for d in deals], ["트리니티항공"])


if __name__ == "__main__":
    unittest.main()
