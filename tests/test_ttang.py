"""땡처리닷컴 판매 목록. 행 구조는 2026-10-25 목록 페이지(인천→다낭 에어서울 259,900원)를 줄여 옮겼다."""

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from collector import ttang


def row(dep, dep_name, arr, arr_name, airline, code, via, dates, trip, price):
    return (f'<tr><td><p class="shortCut">{dep_name}</p></td><td><p class="shortCut">{arr_name}</p></td>'
            f'<td class="line2 airlogo"><p><img alt="" src="/x.png">{airline}</p></td><td>{via}</td>'
            f'<td>\n {dates}\n </td><td>{trip}</td>'
            f'<td class="price"><a href="#none">{price}∼</a><div class="tooltip"><li>기본운임: 10,000원</li></div></td>'
            f'<td><a href="#none;" data-adtFare="10000" data-arrCity="{arr}" data-depCity="{dep}" data-airlineCode="{code}">예약</a></td></tr>')


PAGE = ("<table><tbody>"
        + row("ICN", "인천", "DAD", "다낭", "에어서울", "RS", "직항", "2026.10.28~2026.11.29", "왕복", "259,900원")
        + row("PUS", "부산", "DAD", "다낭", "에어부산", "BX", "직항", "2026.11.01~2026.11.30", "왕복", "199,000원")
        + row("ICN", "인천", "CXR", "나트랑(깜란)", "트리니티항공", "TW", "경유", "2026.11.03~2026.12.27", "편도", "199,000원")
        + "</tbody></table>")


class TestParse(unittest.TestCase):
    def test_only_icn_sorted_by_total(self):
        items = ttang.parse(PAGE)
        self.assertEqual([(i["dest_code"], i["price"]) for i in items], [("CXR", 199000), ("DAD", 259900)])
        x = items[0]
        self.assertEqual((x["destination"], x["airline"], x["direct"], x["trip"], x["depart_from"], x["depart_to"]),
                         ("나트랑(깜란)", "트리니티항공", False, "oneway", "2026-11-03", "2026-12-27"))
        self.assertEqual(items[1]["price"], 259900)  # 표시 총액(기본운임이 아니라)


class TestMain(unittest.TestCase):
    def test_once_a_day_and_empty_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ttang.json"
            hist = Path(tmp) / "price_history.json"
            with mock.patch.object(ttang, "OUT", out), mock.patch.object(ttang, "HISTORY", hist), \
                    mock.patch.object(ttang, "fetch", return_value=PAGE) as f:
                ttang.main(date(2026, 10, 25))
                ttang.main(date(2026, 10, 25))
                self.assertEqual(f.call_count, 1)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual((saved["fetched_on"], len(saved["items"])), ("2026-10-25", 2))
            with mock.patch.object(ttang, "OUT", out), mock.patch.object(ttang, "HISTORY", hist), \
                    mock.patch.object(ttang, "fetch", return_value="<html></html>"):
                ttang.main(date(2026, 10, 26))
            again = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual((again["fetched_on"], again["empty_since"], len(again["items"])), ("2026-10-25", "2026-10-26", 2))
            # 이력은 받은 날만 쌓인다 (0건인 날은 더하지 않는다)
            h = json.loads(hist.read_text(encoding="utf-8"))
            self.assertEqual({k: list(v["days"]) for k, v in h["dests"].items()},
                             {"CXR:oneway": ["2026-10-25"], "DAD": ["2026-10-25"]})


class TestHistory(unittest.TestCase):
    def item(self, code, price, trip="roundtrip", airline="에어서울"):
        return {"destination": code, "dest_code": code, "airline": airline, "trip": trip, "price": price}

    def test_daily_low_per_destination_and_trip(self):
        h = ttang.add_history({}, [self.item("DAD", 259900), self.item("DAD", 199000, airline="진에어"),
                                   self.item("DAD", 99000, trip="oneway")], date(2026, 10, 25))
        self.assertEqual(h["dests"]["DAD"]["days"], {"2026-10-25": {"price": 199000, "airline": "진에어"}})
        self.assertEqual(h["dests"]["DAD:oneway"]["days"]["2026-10-25"]["price"], 99000)
        # 같은 날 다시 받으면 더 싼 값만 남긴다
        h = ttang.add_history(h, [self.item("DAD", 209000)], date(2026, 10, 25))
        self.assertEqual(h["dests"]["DAD"]["days"]["2026-10-25"]["price"], 199000)

    def test_drops_days_older_than_keep(self):
        h = ttang.add_history({}, [self.item("DAD", 199000)], date(2026, 7, 1))
        h = ttang.add_history(h, [self.item("CXR", 179900)], date(2026, 7, 1) + timedelta(days=ttang.HISTORY_DAYS))
        self.assertEqual(list(h["dests"]), ["CXR"])  # 기록이 다 빠진 도착지는 지운다


if __name__ == "__main__":
    unittest.main()
