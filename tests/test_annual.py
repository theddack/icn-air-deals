"""연례 세일 예고 (collector/annual.py). 행사는 형식만 흉내 낸 예시다."""

import unittest
from datetime import date

from collector import annual

SEED = {"sales": [{"airline_id": "7c", "airline": "가항공", "name": "큰 특가", "keywords": ["큰특가"],
                   "windows": [{"from": "01-20", "to": "02-15", "seen": ["2024-01", "2026-02"]}]}]}


def deal(**kw):
    base = {"id": "d1", "airline_id": "7c", "airline": "가항공", "event_name": "큰 특가", "headline": "",
            "sale_start": "2026-01-22", "sale_end": "2026-01-28", "first_seen": "2026-01-20T09:00:00+09:00",
            "last_published": "2026-01-20", "conflicts": []}
    return {**base, **kw}


class AnnualTest(unittest.TestCase):
    def test_seed_window_ahead(self):
        out = annual.expected(SEED, None, [], date(2027, 1, 10))
        self.assertEqual([(x["name"], x["start"]) for x in out], [("큰 특가", "2027-01-20")])
        self.assertIn("2024·2026", out[0]["basis"])

    def test_too_far_or_past(self):
        self.assertEqual(annual.expected(SEED, None, [], date(2026, 12, 20)), [])
        self.assertEqual(annual.expected(SEED, None, [], date(2027, 1, 25)), [])

    def test_suppressed_when_already_shown(self):
        live = deal(sale_start="2027-01-08", sale_end="2027-01-30", last_published="2027-01-08")
        self.assertEqual(annual.expected(SEED, None, [live], date(2027, 1, 10)), [])

    def test_history_last_year(self):
        hist = annual.remember({}, [deal(airline_id="lj", airline="나항공", event_name="여름 마켓",
                                         sale_start="2026-07-13", sale_end="2026-07-16")], date(2026, 7, 13))
        out = annual.expected(None, hist, [], date(2027, 7, 1))
        self.assertEqual([(x["airline"], x["start"], x["basis"]) for x in out], [("나항공", "2027-07-13", "2026년 기록 기준")])

    def test_history_not_duplicating_seed(self):
        hist = annual.remember({}, [deal(sale_start="2026-01-22")], date(2026, 1, 22))
        out = annual.expected(SEED, hist, [], date(2027, 1, 12))
        self.assertEqual(len(out), 1)

    def test_remember_skips_undated_and_conflicts(self):
        hist = annual.remember({}, [deal(sale_start=None), deal(id="d2", conflicts=["sale"]), deal(id="d3", airline_id="multi")],
                               date(2026, 1, 22))
        self.assertEqual(hist["events"], {})


class PriceFromTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(annual.price_from("153만7800원부터"), 1537800)
        self.assertEqual(annual.price_from("4만9400원부터"), 49400)
        self.assertEqual(annual.price_from("190,000원부터"), 190000)
        self.assertEqual(annual.price_from("7만원대부터"), 70000)
        self.assertIsNone(annual.price_from("최대 3만원 할인"))
        self.assertIsNone(annual.price_from("최대 30%"))
        self.assertIsNone(annual.price_from(None))

    def test_remember_keeps_lowest_price_and_dests(self):
        d = deal(discount="5만원부터", routes=[{"origin": "인천(ICN)", "destination": "후쿠오카(FUK)"}])
        h = annual.remember({}, [d], date(2026, 1, 22))
        h = annual.remember(h, [deal(discount="4만9400원부터")], date(2026, 1, 23))
        h = annual.remember(h, [deal(discount="최대 30%")], date(2026, 1, 24))
        (rec,) = h["events"].values()
        self.assertEqual(rec["price_from"], 49400)
        self.assertEqual(rec["dests"], ["후쿠오카"])  # 나중 수집에 노선이 없어도 앞서 본 노선을 남긴다
