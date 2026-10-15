import unittest
from datetime import date

from collector.main import enrich
from collector.merge import cluster_articles
from collector.status import should_keep, status


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

    def test_hotel_deal_has_no_airport(self):
        d = cluster_articles([art("여기어때, 가평 숙소 대상 최대 3만원 할인 쿠폰 제공", "2026-10-02")])[0]
        self.assertEqual((d["section"], d["from_icn"], d["airline"]), ("hotel", None, "여기어때"))

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
        self.assertFalse(should_keep(open_ended, date(2026, 7, 23)))


if __name__ == "__main__":
    unittest.main()
