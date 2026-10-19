"""언론사 RSS 요약문. 문장은 2026-10-15 트래블데일리 RSS의 세부퍼시픽항공 '10.10 특가' 기사 요약문에서 짧게 옮겼다."""

import unittest
from datetime import date

from collector import extract as x
from collector.main import _summary_fill, attach_outlet_items, enrich
from collector.merge import cluster_articles
from collector.sources.outlet_rss import FEEDS, _pub, parse

SUMMARY = ("세부퍼시픽항공이 ‘10.10 특가 행사’를 통해 프로모션을 선보인다. "
           "이번 프로모션은 2026년 10월 8일부터 14일까지 진행되며 세부행 항공권을 편도 총액 최저 10만 100원부터 구매할 수 있다. "
           "탑승 기간은 2027년 2월 1일부터 6월 30일까지다.")


class TestSummaryFacts(unittest.TestCase):
    def test_sale_and_travel_sentences_are_kept_apart(self):
        f, e = x.facts_from_summary(SUMMARY, date(2026, 10, 10))
        self.assertEqual((f["sale_start"], f["sale_end"]), (date(2026, 10, 8), date(2026, 10, 14)))
        self.assertEqual((f["travel_start"], f["travel_end"]), (date(2027, 2, 1), date(2027, 6, 30)))
        self.assertEqual((f["discount"], f["destination"]), ("10만100원부터", "세부(CEB)"))
        self.assertTrue(all(len(v) <= x.EVIDENCE_MAX + 2 for v in e.values()))  # 말줄임표 포함

    def test_travel_only_sentence_is_not_sale_period(self):
        f, _ = x.facts_from_summary("진에어가 특가를 연다. 탑승 기간은 12월 1일부터 31일까지다.", date(2026, 10, 10))
        self.assertNotIn("sale_start", f)
        self.assertEqual(f["travel_start"], date(2026, 12, 1))

    def test_pub_date_formats(self):
        self.assertEqual(_pub("2026-10-14 22:18:44"), "2026-10-14")
        self.assertEqual(_pub("Tue, 14 Oct 2026 22:18:44 +0900"), "2026-10-14")
        # 문체부 RSS는 시간대를 'KST'로 적는다. 밤 11시 기사가 UTC로 읽혀 날짜가 바뀌면 안 된다
        self.assertEqual(_pub("Mon, 19 Oct 2026 23:30:00 KST"), "2026-10-19")

    def test_placeholder_summary_is_empty(self):
        xml = ("<rss><channel><item><title><![CDATA[2026 숙박세일 페스타]]></title>"
               "<link>http://www.mcst.go.kr/x</link><description><![CDATA[\n\t\tEMPTY_CLOB()\n\t]]></description>"
               "<pubDate>Mon, 19 Oct 2026 08:06:37 KST</pubDate></item></channel></rss>").encode("utf-8")
        it = parse(xml, "문화체육관광부")[0]
        self.assertEqual((it["summary"], it["published"]), ("", "2026-10-19"))

    def test_feed_list(self):
        urls = [u for _, u in FEEDS]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(len({n for n, _ in FEEDS}), len(FEEDS))
        self.assertTrue(all(u.startswith("https://") for u in urls))


def item(title, summary=SUMMARY, pub="2026-10-10", url="https://outlet.example/1"):
    return {"outlet": "트래블데일리", "title": title, "summary": summary, "url": url, "published": pub}


class TestAttach(unittest.TestCase):
    def test_matches_existing_article_and_fills_only_missing_fields(self):
        g = {"title": "세부퍼시픽항공, ‘10.10 특가’ 최대 20%", "outlet": "구글", "url": "g1", "published": "2026-10-10", "first_seen": "x"}
        new, n = attach_outlet_items([g], [item("세부퍼시픽항공 ‘10.10 특가’ 최대 20%")], "t")
        self.assertEqual((new, n), ([], 1))
        a = enrich(g)
        self.assertEqual(a["discount"], "최대 20%")             # 제목 값이 우선
        self.assertEqual(a["sale_start"], "2026-10-08")         # 비어 있던 값은 요약문에서
        d = cluster_articles([a])[0]
        self.assertEqual(d["evidence"]["sale"]["url"], "https://outlet.example/1")
        self.assertTrue(d["evidence"]["sale"]["title"].startswith("트래블데일리 요약문:"))
        self.assertEqual(d["evidence"]["discount"]["url"], "g1")

    def test_new_event_article_from_outlet_only(self):
        new, n = attach_outlet_items([], [item("세부퍼시픽항공 ‘10.10 특가’"), item("오늘의 날씨", url="u2")], "t")
        self.assertEqual([a["title"] for a in new], ["세부퍼시픽항공 ‘10.10 특가’"])
        self.assertNotIn("summary", new[0])  # 요약문 원문은 저장하지 않는다
        self.assertEqual(new[0]["summary_facts"]["fields"]["sale_end"], "2026-10-14")

    def test_same_title_twice_is_added_once(self):
        new, _ = attach_outlet_items([], [item("세부퍼시픽항공 ‘10.10 특가’"), item("세부퍼시픽항공 '10.10 특가'", url="u2")], "t")
        self.assertEqual(len(new), 1)

    def test_title_start_only_gets_end_from_summary(self):
        # 제목 '8일부터'(시작만) + 요약문 '8일부터 14일까지' → 종료일만 요약문에서
        g = {"title": "세부퍼시픽항공, 8일부터 ‘10.10 특가’", "outlet": "구글", "url": "g1", "published": "2026-10-07", "first_seen": "x"}
        attach_outlet_items([g], [item("세부퍼시픽항공 8일부터 ‘10.10 특가’", pub="2026-10-07")], "t")
        a = enrich(g)
        self.assertEqual((a["sale_start"], a["sale_end"]), ("2026-10-08", "2026-10-14"))
        self.assertTrue(a["_src"]["sale"]["title"].startswith("제목 + 트래블데일리 요약문:"))


class TestSummaryFill(unittest.TestCase):
    def test_fills_missing_side_when_known_side_agrees(self):
        self.assertEqual(_summary_fill("sale", ["2026-10-08", None], ["2026-10-08", "2026-10-14"]), ["2026-10-08", "2026-10-14"])
        self.assertEqual(_summary_fill("sale", ["2026-10-08", None], [None, "2026-10-14"]), ["2026-10-08", "2026-10-14"])

    def test_conflicting_known_side_fills_nothing(self):
        self.assertIsNone(_summary_fill("sale", ["2026-10-08", None], ["2026-10-01", "2026-10-05"]))

    def test_end_before_start_fills_nothing(self):
        self.assertIsNone(_summary_fill("travel", ["2026-12-01", None], [None, "2026-11-30"]))

    def test_title_complete_or_summary_empty(self):
        self.assertIsNone(_summary_fill("sale", ["2026-10-08", "2026-10-14"], ["2026-10-01", "2026-10-20"]))
        self.assertIsNone(_summary_fill("sale", [None, None], [None, None]))
        self.assertEqual(_summary_fill("sale", [None, None], ["2026-10-08", "2026-10-14"]), ["2026-10-08", "2026-10-14"])

    def test_route_side_fill(self):
        self.assertEqual(_summary_fill("route", [None, "세부(CEB)"], ["인천(ICN)", None]), ["인천(ICN)", "세부(CEB)"])
        self.assertIsNone(_summary_fill("route", [None, "세부(CEB)"], ["인천(ICN)", "보홀(TAG)"]))


if __name__ == "__main__":
    unittest.main()
