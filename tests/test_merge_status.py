import unittest
from datetime import date

from collector.main import build_deals, enrich
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
