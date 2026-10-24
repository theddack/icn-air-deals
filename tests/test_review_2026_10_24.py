"""2026-10-24 소스 검토에서 고친 것: 연말 날짜, 빈 시간표 덮어쓰기, 진행 중 행사 기사 보존, http(s)가 아닌 주소."""

import unittest
from datetime import date

from collector import extract as x
from collector.flights import suspicious
from collector.main import merge_articles
from collector.sources.outlet_rss import parse


class TestYearEnd(unittest.TestCase):
    def test_january_article_december_date_is_last_year(self):
        self.assertEqual(x.extract_dates("신년 특가 12월 29일부터 1월 4일까지", date(2027, 1, 2)),
                         (date(2026, 12, 29), date(2027, 1, 4)))
        self.assertEqual(x.extract_dates_en("Sale Dec 29 - Jan 4 hotel stays", date(2027, 1, 2)),
                         (date(2026, 12, 29), date(2027, 1, 4)))

    def test_existing_windows_unchanged(self):
        self.assertEqual(x.extract_dates("1월 5일까지 얼리버드", date(2026, 10, 24)), (None, date(2027, 1, 5)))
        self.assertEqual(x.extract_dates("12월 29일부터 신년 특가", date(2026, 12, 20)), (date(2026, 12, 29), None))


class TestFlightsGuard(unittest.TestCase):
    def test_empty_or_shrunken_schedule_is_not_saved(self):
        self.assertIsNotNone(suspicious({"schedule": [], "coverage": None}, 4000))
        self.assertIsNotNone(suspicious({"schedule": [{}] * 100, "coverage": {"full_until": "x"}}, 4000))
        self.assertIsNone(suspicious({"schedule": [{}] * 1700, "coverage": {"full_until": "x"}}, 4000))  # 시즌 교체 수준
        self.assertIsNone(suspicious({"schedule": [{}] * 10, "coverage": {"full_until": "x"}}, 0))      # 첫 수집


class TestKeepRunningDeals(unittest.TestCase):
    def test_old_article_kept_while_sale_continues(self):
        art = lambda t, pub: {"title": t, "outlet": "o", "url": t, "published": pub, "first_seen": pub}
        running = art("에어부산, 11월 30일까지 얼리버드 특가", "2026-09-01")
        over = art("에어부산, 9월 10일까지 특가", "2026-09-01")
        too_old = art("에어부산, 12월 31일까지 특가", "2026-03-01")
        kept, _ = merge_articles([running, over, too_old], [], date(2026, 10, 24))
        self.assertEqual([a["title"] for a in kept], [running["title"]])


class TestUrls(unittest.TestCase):
    def test_non_http_links_are_dropped(self):
        xml = ("<rss><channel>"
               "<item><title>제주항공 특가</title><link>javascript:alert(1)</link><description>x</description></item>"
               "<item><title>진에어 특가</title><link></link><description>x</description></item>"
               "<item><title>에어부산 특가</title><link>https://news.example/1</link><description>x</description></item>"
               "</channel></rss>").encode("utf-8")
        self.assertEqual([i["title"] for i in parse(xml, "o")], ["에어부산 특가"])


if __name__ == "__main__":
    unittest.main()
