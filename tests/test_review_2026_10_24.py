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


# ---------------------------------------------------------------- 2026-10-25 남은 검토 항목

import json
import tempfile
from pathlib import Path
from unittest import mock

from collector import secretflying
from collector.main import _same_story, attach_outlet_items


class TestSameStory(unittest.TestCase):
    def test_short_title_does_not_attach_to_other_event(self):
        # 짧은 제목이 긴 지난 기사 제목에 포함돼도 길이 비율·발행일이 다르면 같은 기사로 보지 않는다
        self.assertFalse(_same_story("에어부산얼리버드특가진행", "에어부산얼리버드특가진행동남아노선최대30할인연말까지", "2026-09-01", "2026-10-20"))
        self.assertFalse(_same_story("에어부산얼리버드특가진행", "에어부산얼리버드특가진행동남아노선최대30할인연말까지", "2026-10-20", "2026-10-20"))
        self.assertTrue(_same_story("세부퍼시픽항공1010특가최대20", "세부퍼시픽항공1010특가최대20할인", "2026-10-10", "2026-10-11"))

    def test_attach_uses_same_story(self):
        old = {"title": "에어부산 얼리버드 특가 진행…동남아 노선 최대 30% 할인 연말까지", "url": "g1", "published": "2026-09-01", "first_seen": "x"}
        item = {"outlet": "o", "title": "에어부산 얼리버드 특가 진행", "summary": "", "url": "https://o.example/1", "published": "2026-10-20"}
        new, enriched = attach_outlet_items([old], [item], "t")
        self.assertEqual((len(new), enriched), (1, 0))  # 지난 기사에 붙지 않고 새 기사로 들어간다


class TestTravelEnd(unittest.TestCase):
    def test_day_without_month_rolls_forward(self):
        self.assertEqual(x.extract_travel("5일까지 탑승 특가", date(2026, 10, 24)), (None, date(2026, 11, 5)))
        self.assertEqual(x.extract_travel("25일까지 탑승 특가", date(2026, 10, 24)), (None, date(2026, 10, 25)))

    def test_wrapping_month_range_written_inside_it(self):
        self.assertEqual(x.extract_travel("12~2월 탑승 특가", date(2027, 1, 5)), (date(2026, 12, 1), date(2027, 2, 28)))
        self.assertEqual(x.extract_travel("12~2월 탑승 특가", date(2026, 10, 24)), (date(2026, 12, 1), date(2027, 2, 28)))


class TestSecretFlyingEmpty(unittest.TestCase):
    def test_zero_results_retry_and_keep_deals(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sf.json"
            prev = {"fetched_on": "2026-10-24", "deals": [{"url": "u", "first_seen": "2026-10-20", "last_seen": "2026-10-24"}]}
            out.write_text(json.dumps(prev), encoding="utf-8")
            with mock.patch.object(secretflying, "OUT", out), mock.patch.object(secretflying, "fetch", return_value="<html></html>") as f:
                secretflying.main(date(2026, 10, 25))
                secretflying.main(date(2026, 10, 25))  # 0건이면 같은 날 다시 시도한다
                self.assertEqual(f.call_count, 2)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual((saved["fetched_on"], saved["empty_since"], len(saved["deals"])), ("2026-10-24", "2026-10-25", 1))
