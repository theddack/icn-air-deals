"""인천공항 시간표 정규화. 입력 형식은 2026-10-15 실제 응답(probe-icn-api 실행 38683051186)의 필드를 그대로 쓴다."""

import unittest
from datetime import date, datetime

from collector.flights import build, coverage, flights_on, normalize_schedule, normalize_status
from collector.status import KST

DAYS = dict(monday="Y", tuesday="Y", wednesday="Y", thursday="Y", friday="Y", saturday="Y", sunday="Y")


def sched(flight, st, first, last, **days):
    return {"flightid": flight, "airline": "제주항공", "st": st, "firstdate": first, "lastdate": last,
            "airportcode": "FUK", "airport": "후쿠오카", "season": "S26", **{**DAYS, **days}}


class TestSchedule(unittest.TestCase):
    def test_normalize(self):
        r = normalize_schedule([sched("7C1401", "0630", "20260329", "20261024", sunday="N")])[0]
        self.assertEqual((r["flight"], r["time"], r["first"], r["last"], r["days"]),
                         ("7C1401", "06:30", "2026-03-29", "2026-10-24", "1111110"))

    def test_bad_rows_are_skipped(self):
        self.assertEqual(normalize_schedule([sched("X1", "63", "20260329", "20261024"),
                                             sched("X2", "0630", "2026", "20261024")]), [])

    def test_flights_on_respects_period_and_weekday(self):
        rows = normalize_schedule([sched("A1", "0630", "20261001", "20261024", saturday="N"),
                                   sched("A2", "0700", "20261025", "20261205")])
        self.assertEqual([r["flight"] for r in flights_on(rows, date(2026, 10, 16))], ["A1"])   # 금
        self.assertEqual([r["flight"] for r in flights_on(rows, date(2026, 10, 17))], [])       # 토 비운항
        self.assertEqual([r["flight"] for r in flights_on(rows, date(2026, 11, 2))], ["A2"])

    def test_coverage_uses_most_common_end(self):
        rows = normalize_schedule([sched("A1", "0630", "20260329", "20261024"),
                                   sched("A2", "0700", "20260329", "20261024"),
                                   sched("A3", "0800", "20261001", "20261205")])
        self.assertEqual(coverage(rows, date(2026, 10, 15)),
                         {"from": "2026-10-15", "full_until": "2026-10-24", "partial_until": "2026-12-05"})


class TestStatus(unittest.TestCase):
    def test_normalize_status(self):
        items = [
            {"flightId": "9G401", "codeshare": "Master", "masterFlightId": None, "passengerOrCargo": "Passenger",
             "scheduleDatetime": "202610120010", "estimatedDatetime": "202610120002", "remark": "출발", "gateNumber": "111"},
            {"flightId": "VN401", "codeshare": "Slave", "masterFlightId": "9G401", "passengerOrCargo": "Passenger",
             "scheduleDatetime": "202610120010", "estimatedDatetime": "202610120002", "remark": "출발", "gateNumber": "111"},
            {"flightId": "KE9001", "codeshare": "Master", "passengerOrCargo": "Cargo",
             "scheduleDatetime": "202610120100", "estimatedDatetime": None, "remark": None},
        ]
        s = normalize_status(items)
        self.assertEqual(sorted(s["2026-10-12"]), ["9G401", "VN401"])  # 화물편 제외
        self.assertEqual(s["2026-10-12"]["9G401"]["estimated"], "00:02")
        self.assertEqual(s["2026-10-12"]["VN401"]["codeshare_of"], "9G401")

    def test_codeshare_marked_on_schedule_and_past_days_dropped(self):
        st = [{"flightId": "VN401", "codeshare": "Slave", "masterFlightId": "9G401", "passengerOrCargo": "Passenger",
               "scheduleDatetime": "202610120010", "estimatedDatetime": None, "remark": None},
              {"flightId": "9G401", "codeshare": "Master", "masterFlightId": None, "passengerOrCargo": "Passenger",
               "scheduleDatetime": "202610160010", "estimatedDatetime": None, "remark": None}]
        d = build([sched("VN401", "0010", "20260329", "20261024"), sched("9G401", "0010", "20260329", "20261024"),
                   sched("ZZ1", "0100", "20260329", "20261024")], st, datetime(2026, 10, 15, 13, 0, tzinfo=KST))
        by = {r["flight"]: (r["codeshare_of"], r["status_seen"]) for r in d["schedule"]}
        self.assertEqual(by, {"VN401": ("9G401", True), "9G401": (None, True), "ZZ1": (None, False)})
        self.assertEqual(sorted(d["status"]), ["2026-10-16"])  # 10/12는 지난 날짜

    def test_build_ranges(self):
        d = build([sched("7C1401", "0630", "20260329", "20261024")],
                  [{"flightId": "7C1401", "codeshare": "Master", "passengerOrCargo": "Passenger",
                    "scheduleDatetime": "202610150630", "estimatedDatetime": "202610150645", "remark": "지연"}],
                  datetime(2026, 10, 15, 13, 0, tzinfo=KST))
        self.assertEqual(d["status_range"], {"from": "2026-10-15", "to": "2026-10-15"})
        self.assertEqual(d["coverage"]["full_until"], "2026-10-24")
        self.assertEqual(d["seasons"], ["S26"])

    def test_status_failure_reuses_previous_file(self):
        # 2026-10-20 실제 사례: 운항 현황이 TLS 시간 초과로 실패해 공동운항·지연 정보가 빈 값으로 덮였다
        now = datetime(2026, 10, 16, 9, 0, tzinfo=KST)
        prev = build([sched("VN401", "0010", "20260329", "20261024"), sched("9G401", "0010", "20260329", "20261024")],
                     [{"flightId": "VN401", "codeshare": "Slave", "masterFlightId": "9G401", "passengerOrCargo": "Passenger",
                       "scheduleDatetime": "202610160010"},
                      {"flightId": "9G401", "codeshare": "Master", "passengerOrCargo": "Passenger",
                       "scheduleDatetime": "202610150010", "estimatedDatetime": "202610150030", "remark": "출발"},
                      {"flightId": "9G401", "codeshare": "Master", "passengerOrCargo": "Passenger",
                       "scheduleDatetime": "202610160010", "estimatedDatetime": "202610160040", "remark": "지연"}],
                     datetime(2026, 10, 15, 22, 0, tzinfo=KST))
        d = build([sched("VN401", "0010", "20260329", "20261024"), sched("9G401", "0010", "20260329", "20261024"),
                   sched("NEW1", "0100", "20260329", "20261024")], [], now, previous=prev)
        by = {r["flight"]: (r["codeshare_of"], r["status_seen"]) for r in d["schedule"]}
        self.assertEqual(by, {"VN401": ("9G401", True), "9G401": (None, True), "NEW1": (None, False)})
        self.assertEqual(sorted(d["status"]), ["2026-10-16"])  # 지난 날짜(10/15)는 이어 쓰지 않는다
        self.assertEqual(d["status"]["2026-10-16"]["9G401"]["remark"], "지연")
        self.assertEqual(d["status_from"], prev["generated_at"])

    def test_retry_then_give_up(self):
        from unittest import mock
        from collector import flights
        calls = []

        def boom(*a):
            calls.append(1)
            raise flights.ApiError("HTTP 503", retryable=True)
        with mock.patch.object(flights, "_call_once", boom), mock.patch.object(flights.time, "sleep"):
            with self.assertRaises(flights.ApiError):
                flights._call("k", "p", 1)
        self.assertEqual(len(calls), 3)
        calls.clear()

        def bad_key(*a):
            calls.append(1)
            raise flights.ApiError("HTTP 401", retryable=False)
        with mock.patch.object(flights, "_call_once", bad_key), mock.patch.object(flights.time, "sleep"):
            with self.assertRaises(flights.ApiError):
                flights._call("k", "p", 1)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
