"""해외 호텔 시범(2026-10-15). 영어 제목은 같은 날 영어판 Google 뉴스 '호텔 할인' 검색 결과에서 옮겼다."""

import unittest
from datetime import date

from collector import extract as x
from collector.main import enrich
from collector.merge import cluster_articles

EN_SALES = ["ALL Accor+ Explorer 30% To 50% Off “Red Hot Rooms” October 2026 Update",
            "Save 15% on luxury resorts, with this Club Med discount code",
            "10.10 travel sale: Where to score discounted flights, hotel stays and more this October"]
EN_NOT_SALES = ["Hyatt promo: Earn 1.5X Aeroplan points on stays in addition to Hyatt points",   # 포인트
                "New Marriott Bonvoy Promotion: 1,000 Points per Stay in Canada, Plus Ongoing Offers",
                "Raffles Hotel Singapore Announces New Leadership Promotion",                  # 인사
                "Hilton appeals loss in fight with ATO over $173M hotel sale",                 # 매각 소송
                "Fancy running a hotel in Singapore? This boutique farmstay in Changi is now up for sale",
                "Current hotel promotions for October 2026",                                   # 가격 할인 표현 없음
                # 시범 첫 수집(2026-10-15)에서 걸러 낸 유형: 할인 코드 모음, 포인트 숙박, 박람회
                "Best Away Resorts discount codes 2026: Save 15% on your next break",
                "IHG Discount Code: Hotel Deals & Coupons for October 2026",
                "Hotels.com discount code: Exclusive 6% off bookings",
                "Save 15% on IHG award stays at new hotels",
                "Megaworld Global Hotels and Resorts invites travelers to explore PH at Travel Sale Expo 2026"]


def art(title, pub="2026-10-07", lang=None, url=None):
    a = {"title": title, "outlet": "test", "url": url or title, "published": pub, "first_seen": pub}
    if lang:
        a["lang"] = lang
    return enrich(a)


class TestEnglish(unittest.TestCase):
    def test_price_discounts_only(self):
        self.assertEqual([x.is_hotel_sale_en(t) for t in EN_SALES], [True] * 3)
        self.assertEqual([x.is_hotel_sale_en(t) for t in EN_NOT_SALES], [False] * len(EN_NOT_SALES))
        self.assertIsNone(x.category_of(EN_NOT_SALES[0], "en"))
        self.assertIsNone(x.category_of(EN_SALES[0]))  # 한국어 판정으로는 받지 않는다

    def test_discount_dates_regions(self):
        self.assertEqual(x.extract_discount_en(EN_SALES[0]), "최대 50%")
        self.assertEqual(x.extract_discount_en(EN_SALES[1]), "15% 할인")
        self.assertEqual(x.extract_dates_en("Accor flash sale: 40% off hotels in Asia Pacific, Oct 7–20", date(2026, 10, 7)),
                         (date(2026, 10, 7), date(2026, 10, 20)))
        self.assertEqual(x.extract_dates_en("Hilton sale ends Nov 3", date(2026, 10, 7)), (None, date(2026, 11, 3)))
        self.assertEqual(x.regions_en("Accor flash sale: 40% off hotels in Asia Pacific"), ["아시아·태평양"])

    def test_english_deal_is_overseas_trial_and_keeps_title(self):
        d = cluster_articles([art(EN_SALES[1], lang="en")])[0]
        self.assertEqual((d["airline"], d["scope"], d["lang"], d["trial"], d["discount"]), ("클럽메드", "overseas", "en", True, "15% 할인"))
        self.assertEqual(d["headline"], EN_SALES[1])  # 번역하지 않는다


class TestKoreanOverseas(unittest.TestCase):
    def test_brandless_overseas_hotel_sale(self):
        t = "겨울방학·연말 수요 겨냥…괌 호텔 5곳 공동 프로모션 진행"
        self.assertEqual(x.category_of(t), "hotel")
        d = cluster_articles([art(t)])[0]
        self.assertEqual((d["airline"], d["scope"], d["trial"]), ("브랜드 미확인", "overseas", True))

    def test_scope(self):
        self.assertEqual(x.hotel_scope("롯데호텔앤리조트, 태국 두짓과 맞손…18개국 60개 호텔서 10% 할인"), "overseas")
        d = cluster_articles([art("강원도, 숙박세일페스타 가을편…최대 7만원 할인")])[0]
        self.assertEqual((d["scope"], d["trial"]), ("domestic", False))

    def test_trend_and_branded_domestic_articles_are_not_overseas_deals(self):
        self.assertIsNone(x.category_of("짧은 연휴 어디로 갈까…국내 숙박 할인·일본 소도시 여행 경쟁"))
        self.assertIsNone(x.category_of("대구 메리어트 호텔, 베트남 미식 여행 프로모션"))

    def test_brandless_articles_are_never_merged(self):
        deals = cluster_articles([art("Mandai Rainforest Resort Marks First Anniversary With Up to 45% OFF Stays", "2026-10-07", "en", "u1"),
                                  art("10.10 travel sale: Where to score discounted flights, hotel stays and more", "2026-10-08", "en", "u2")])
        self.assertEqual(len(deals), 2)

    def test_domestic_brandless_still_ignored(self):
        # 브랜드 없는 국내 숙박 기사는 예전처럼 받지 않는다 (지자체 쿠폰 등 잡음이 많다)
        self.assertIsNone(x.category_of("경남도, 가을 여행객에 18개 시군 숙박 할인쿠폰…최대 7만원"))

    def test_flight_article_with_overseas_place_stays_flight(self):
        self.assertEqual(x.category_of("에어서울, 인스파이어와 맞손…탑승객 투숙하면 최대 15% 할인"), "flight")


if __name__ == "__main__":
    unittest.main()
