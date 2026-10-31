"""텔레그램 알림 (2026-10-27 기획): 시간대별 브리핑, 예약 지연 보완, 재발송 방지, 행사 id 변경, API 실패.
행사는 형식만 흉내 낸 예시다."""

import unittest
from datetime import datetime

from collector import notify
from collector.status import KST


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=KST)


def deal(i, **kw):
    base = {"id": f"d{i}", "airline_id": "7c", "section": "flight", "airline": "제주항공", "kind": "domestic",
            "verification": "news", "event_name": f"행사 {i}", "headline": f"제주항공 행사 {i}",
            "routes": [{"origin": "인천(ICN)", "destination": "오사카(KIX)"}], "discount": "최대 30%",
            "sale_start": "2026-10-20", "sale_end": "2026-11-10", "from_icn": "yes", "conflicts": [],
            "first_seen": "2026-10-20T07:20:00+09:00", "last_published": "2026-10-26",
            "official_url": "https://www.jejuair.net/", "articles": [{"url": f"https://news.example/{i}"}]}
    return {**base, **kw}


STARTED = {"started": "2026-10-25T00:00:00+09:00", "events": {}, "slots": {}}


class Base(unittest.TestCase):
    def go(self, deals, state, now, generated=None, sender=None):
        out = []
        data = {"deals": deals, "generated_at": generated or now, "stats": {}}
        st, err = notify.run(data, state, at(now), sender or out.append)
        return st, out, err


class TestSlots(Base):
    def test_no_send_outside_hours(self):
        st, out, _ = self.go([deal(1, first_seen="2026-10-27T07:20:00+09:00")], STARTED, "2026-10-27T07:30")
        self.assertEqual(out, [])

    def test_morning_briefing_sections(self):
        deals = [deal(1, sale_start="2026-10-27", sale_end="2026-10-31"),          # 오늘 시작
                 deal(2, sale_start="2026-10-30", sale_end="2026-11-05"),          # D-3
                 deal(3, first_seen="2026-10-27T09:20:00+09:00")]                  # 신규
        st, out, _ = self.go(deals, STARTED, "2026-10-27T09:40")
        self.assertEqual(len(out), 1)
        m = out[0]
        self.assertIn("오늘의 여행 할인 브리핑", m)
        self.assertIn("10월 27일 화요일", m)
        self.assertLess(m.index("오늘 판매 시작"), m.index("곧 시작하는 행사"))
        self.assertIn("10/30 판매 시작 · D-3", m)
        self.assertIn("새로 발견한 할인", m)
        self.assertIn("확인 상태: 기사 기준", m)
        self.assertNotIn("기사 여러 건", m)
        self.assertNotIn("뉴스", m)
        self.assertEqual(st["slots"]["2026-10-27"]["morning"], "sent")

    def test_one_message_per_slot_and_new_waits_for_next_slot(self):
        st, out, _ = self.go([deal(3, first_seen="2026-10-27T09:20:00+09:00")], STARTED, "2026-10-27T09:40")
        self.assertEqual(len(out), 1)
        later = [deal(3, first_seen="2026-10-27T09:20:00+09:00"), deal(4, first_seen="2026-10-27T11:00:00+09:00")]
        st, out, _ = self.go(later, st, "2026-10-27T12:00")      # 같은 오전 시간대 → 보내지 않음
        self.assertEqual(out, [])
        st, out, _ = self.go(later, st, "2026-10-27T14:10")      # 오후 → d4만
        self.assertEqual(len(out), 1)
        self.assertIn("행사 4", out[0])
        self.assertNotIn("행사 3", out[0])

    def test_empty_slot_sends_nothing(self):
        st, out, _ = self.go([deal(1)], STARTED, "2026-10-27T09:40")
        self.assertEqual(out, [])
        self.assertEqual(st["slots"]["2026-10-27"]["morning"], "empty")

    def test_evening_closing_and_tomorrow_start(self):
        deals = [deal(1, sale_end="2026-10-27"), deal(2, sale_end="2026-10-28"),
                 deal(3, sale_start="2026-10-28", sale_end="2026-11-02")]
        st = {**STARTED, "slots": {"2026-10-27": {"morning": "sent", "afternoon": "sent"}}}
        _, out, _ = self.go(deals, st, "2026-10-27T20:15")
        m = out[0]
        self.assertIn("오늘의 마감 임박 특가", m)
        self.assertIn("판매 마감: 10/27 (오늘)", m)
        self.assertIn("판매 마감: 10/28 (내일)", m)
        self.assertIn("내일 판매 시작", m)


class TestQuietHours(Base):
    def test_no_send_after_21(self):
        st, out, _ = self.go([deal(1, sale_end="2026-10-28"), deal(2, first_seen="2026-10-27T21:10:00+09:00")],
                             STARTED, "2026-10-27T21:30")
        self.assertEqual(out, [])

    def test_late_night_find_goes_next_morning_and_tomorrow_closing_becomes_today(self):
        deals = [deal(2, first_seen="2026-10-27T22:45:00+09:00"),                 # 22시대 수집에서 발견
                 deal(3, sale_end="2026-10-28"),                                  # 어제 저녁 못 보낸 '내일 마감'
                 deal(4, first_seen="2026-10-27T22:45:00+09:00", sale_end="2026-10-27")]  # 어제 마감 → 제외
        _, out, _ = self.go(deals, STARTED, "2026-10-28T09:20")
        m = out[0]
        self.assertIn("행사 2", m)
        self.assertIn("판매 마감: 10/28 (오늘)", m)
        self.assertNotIn("행사 4", m)


class TestDelay(Base):
    def test_missed_morning_kinds_come_in_afternoon(self):
        # 오전 예약이 실행되지 않음 → 오후 실행이 D-3 안내도 함께 보낸다
        _, out, _ = self.go([deal(2, sale_start="2026-10-30", sale_end="2026-11-05")], STARTED, "2026-10-27T15:30")
        self.assertEqual(len(out), 1)
        self.assertIn("곧 시작하는 행사", out[0])
        self.assertIn("앞 시간대 알림이 늦어", out[0])

    def test_missed_d3_day_caught_next_morning_as_d2(self):
        _, out, _ = self.go([deal(2, sale_start="2026-10-30", sale_end="2026-11-05")], STARTED, "2026-10-28T09:30")
        self.assertIn("10/30 판매 시작 · D-2", out[0])

    def test_already_sent_not_repeated_on_late_run(self):
        d = deal(1, sale_start="2026-10-27", sale_end="2026-10-31")
        st, out, _ = self.go([d], STARTED, "2026-10-27T09:40")
        self.assertEqual(len(out), 1)
        st, out, _ = self.go([d], st, "2026-10-27T15:00")
        self.assertEqual(out, [])


class TestDedupe(Base):
    def test_new_and_start_today_merged_into_one_item(self):
        d = deal(5, sale_start="2026-10-27", first_seen="2026-10-27T09:10:00+09:00")
        st, out, _ = self.go([d], STARTED, "2026-10-27T09:40")
        self.assertEqual(out[0].count("확인 상태:"), 1)
        self.assertEqual(set(st["events"]["d5"]["kinds"]), {"start_today", "new"})

    def test_start_notice_separate_from_upcoming(self):
        d = deal(6, sale_start="2026-10-30", sale_end="2026-11-05")
        st, out, _ = self.go([d], STARTED, "2026-10-27T09:40")
        self.assertIn("곧 시작하는 행사", out[0])
        st, out, _ = self.go([d], st, "2026-10-29T20:10")
        self.assertIn("내일 판매 시작", out[0])
        st, out, _ = self.go([d], st, "2026-10-30T09:10")
        self.assertIn("오늘 판매 시작", out[0])

    def test_id_change_same_event_not_resent(self):
        d = deal(7, first_seen="2026-10-27T09:10:00+09:00")
        st, _, _ = self.go([d], STARTED, "2026-10-27T09:40")
        # 앞선 기사가 묶여 id가 바뀜 (판매 기간·노선·행사명·기사 겹침 그대로)
        moved = {**d, "id": "d7-new", "articles": [{"url": "https://news.example/older"}] + d["articles"]}
        st, out, _ = self.go([moved], st, "2026-10-27T14:20")
        self.assertEqual(out, [])
        self.assertIn("d7-new", st["events"])
        self.assertNotIn("d7", st["events"])

    def test_repeat_event_with_other_sale_dates_is_new(self):
        d = deal(8, sale_start="2026-10-01", sale_end="2026-10-07", first_seen="2026-10-27T09:10:00+09:00")
        st, _, _ = self.go([{**d, "sale_start": "2026-10-27", "sale_end": "2026-11-02"}], STARTED, "2026-10-27T09:40")
        # 같은 이름·노선, 판매 기간만 다른 다음 회차
        nxt = {**d, "id": "d8-2", "sale_start": "2026-11-20", "sale_end": "2026-11-26",
               "first_seen": "2026-10-27T13:00:00+09:00", "articles": [{"url": "https://news.example/8b"}]}
        _, out, _ = self.go([nxt], st, "2026-10-27T14:20")
        self.assertEqual(len(out), 1)

    def test_same_name_only_is_not_same_event(self):
        a = notify.info_of(deal(9, routes=[{"origin": "인천(ICN)", "destination": "오사카(KIX)"}]))
        b = notify.info_of(deal(9, routes=[{"origin": "인천(ICN)", "destination": "다낭(DAD)"}],
                                articles=[{"url": "https://news.example/other"}]))
        self.assertFalse(notify.same_event(a, b))

    def test_undated_same_name_far_apart_is_new_event(self):
        a = notify.info_of(deal(11, sale_start=None, sale_end=None, last_published="2026-09-20"))
        b = notify.info_of(deal(11, sale_start=None, sale_end=None, last_published="2026-10-26",
                                articles=[{"url": "https://news.example/11b"}]))
        self.assertFalse(notify.same_event(a, b))                      # 한 달 뒤 같은 이름 → 다른 회차
        c = notify.info_of(deal(11, sale_start=None, sale_end=None, last_published="2026-10-20",
                                articles=[{"url": "https://news.example/11c"}]))
        self.assertTrue(notify.same_event(c, b))                       # 14일 안 → 같은 행사

    def test_undated_without_name_needs_shared_article(self):
        a = notify.info_of(deal(12, event_name=None, routes=[], sale_start=None, sale_end=None))
        b = notify.info_of(deal(12, event_name=None, routes=[], sale_start=None, sale_end=None,
                                articles=[{"url": "https://news.example/12b"}]))
        self.assertFalse(notify.same_event(a, b))
        shared = notify.info_of(deal(12, event_name=None, routes=[], sale_start=None, sale_end=None,
                                     articles=[{"url": "https://news.example/12"}, {"url": "https://news.example/12c"}]))
        self.assertTrue(notify.same_event(a, shared))

    def test_date_added_links_only_by_shared_article(self):
        before = notify.info_of(deal(13, sale_start=None, sale_end=None))
        after_same = notify.info_of(deal(13, sale_end="2026-11-01",
                                         articles=[{"url": "https://news.example/13"}, {"url": "https://news.example/13b"}]))
        after_other = notify.info_of(deal(13, sale_end="2026-11-01", articles=[{"url": "https://news.example/13c"}]))
        self.assertTrue(notify.same_event(before, after_same))
        self.assertFalse(notify.same_event(before, after_other))

    def test_migrates_old_log(self):
        old = {"started": "2026-10-26", "sent": {"d1": "2026-10-26", "d1:closing": "2026-10-26", "failed:2026-10-26": "x"}}
        st, out, _ = self.go([deal(1, sale_end="2026-10-27")], old, "2026-10-27T09:40")
        self.assertEqual(out, [])
        self.assertIn("closing_today", st["events"]["d1"]["kinds"])


class TestSafety(Base):
    def test_stale_data_no_new_but_dates_ok(self):
        deals = [deal(1, first_seen="2026-10-27T01:00:00+09:00"), deal(2, sale_start="2026-10-27")]
        admin = []
        data = {"deals": deals, "generated_at": "2026-10-26T08:00:00+09:00", "stats": {"failed_queries": 2}}
        out = []
        st, _ = notify.run(data, STARTED, at("2026-10-27T09:40"), out.append, admin.append)
        self.assertEqual(out[0].count("확인 상태:"), 1)
        self.assertIn("오늘 판매 시작", out[0])
        self.assertNotIn("실패", out[0])                       # 수집 실패는 여행 알림에 넣지 않는다
        self.assertTrue(any("시간 전 것" in a for a in admin))
        self.assertTrue(any("실패" in a for a in admin))

    def test_api_failure_keeps_sent_part_and_retries_rest(self):
        many = [deal(i, first_seen="2026-10-27T09:10:00+09:00", event_name="긴 행사 이름 " * 6 + str(i)) for i in range(60)]
        calls = []

        def flaky(text):
            calls.append(text)
            if len(calls) == 2:
                raise TimeoutError()

        st, out, err = self.go(many, STARTED, "2026-10-27T09:40", sender=flaky)
        self.assertIsNotNone(err)
        first = calls[0].count("확인 상태:")
        self.assertEqual(len(st["events"]), first)                       # 첫 메시지 항목만 기록
        self.assertNotEqual(st.get("slots", {}).get("2026-10-27", {}).get("morning"), "sent")
        st, out, err = self.go(many, st, "2026-10-27T10:30")             # 같은 시간대 다음 실행: 남은 것만
        self.assertIsNone(err)
        self.assertEqual(sum(m.count("확인 상태:") for m in out), 60 - first)

    def test_long_message_split_under_limit(self):
        many = [deal(i, first_seen="2026-10-27T09:10:00+09:00", event_name="긴 행사 이름 " * 6 + str(i)) for i in range(60)]
        _, out, _ = self.go(many, STARTED, "2026-10-27T09:40")
        self.assertGreater(len(out), 1)
        self.assertTrue(all(len(m) <= 4096 for m in out))
        self.assertEqual(sum(m.count("확인 상태:") for m in out), 60)

    def test_text_is_escaped_and_official_label(self):
        d = deal(9, routes=[], event_name="<특가> & 이벤트", first_seen="2026-10-27T09:10:00+09:00", verification="official")
        _, out, _ = self.go([d], STARTED, "2026-10-27T09:40")
        self.assertIn("&lt;특가&gt; &amp; 이벤트", out[0])
        self.assertIn("확인 상태: 항공사 공식", out[0])

    def test_no_official_url(self):
        d = deal(10, official_url=None, airline_id="multi", first_seen="2026-10-27T09:10:00+09:00")
        _, out, _ = self.go([d], STARTED, "2026-10-27T09:40")
        self.assertNotIn("공식 홈페이지", out[0])

    def test_first_run_existing_deals_are_not_new(self):
        d = deal(1, first_seen="2026-10-27T08:00:00+09:00")
        st, out, _ = self.go([d], {}, "2026-10-27T09:40")
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()


class SendAllTest(unittest.TestCase):
    """받는 사람 여럿: 동시에 보내고, 한 사람 실패가 다른 사람에게 번지지 않는다."""

    def test_one_failure_does_not_stop_others(self):
        got = []

        def one(chat, text):
            if chat == "bad":
                raise RuntimeError("blocked")
            got.append(chat)

        failed = notify.send_all(["a", "bad", "c"], "안녕", one)
        self.assertEqual(failed, [2])
        self.assertEqual(sorted(got), ["a", "c"])

    def test_all_fail_raises(self):
        def one(chat, text):
            raise RuntimeError("down")

        with self.assertRaises(RuntimeError):
            notify.send_all(["a", "b"], "안녕", one)

    def test_sent_in_parallel(self):
        import threading
        barrier = threading.Barrier(2, timeout=5)

        def one(chat, text):
            barrier.wait()  # 차례로 보내면 여기서 멈춰 시간 초과가 난다

        self.assertEqual(notify.send_all(["a", "b"], "안녕", one), [])


class WeeklyTest(Base):
    """일요일 저녁 주간 요약: 주마다 한 번, 시간대 브리핑과 따로."""
    SUN = "2026-11-01T18:40"

    def deals(self):
        return [deal(1, first_seen="2026-10-28T09:00:00+09:00", sale_start="2026-10-20", sale_end="2026-11-04"),
                deal(2, first_seen="2026-10-10T09:00:00+09:00", sale_start="2026-11-03", sale_end="2026-11-20"),
                deal(3, first_seen="2026-10-10T09:00:00+09:00", sale_start="2026-10-01", sale_end="2026-10-25")]

    def run_at(self, now, state):
        out = []
        data = {"generated_at": at(now).isoformat(), "deals": self.deals()}
        new_state, err = notify.run(data, state, at(now), out.append)
        self.assertIsNone(err)
        return new_state, [t for t in out if "이번 주 여행 할인 요약" in t]

    def test_sections(self):
        sec = notify.weekly_sections(self.deals(), at(self.SUN).date())
        self.assertEqual([d["id"] for d in sec["new"]], ["d1"])
        self.assertEqual([d["id"] for d in sec["start"]], ["d2"])
        self.assertEqual([d["id"] for d in sec["close"]], ["d1"])  # d3은 이미 끝나 빠진다

    def test_sunday_evening_once(self):
        state, weekly = self.run_at(self.SUN, dict(STARTED))
        self.assertEqual(len(weekly), 1)
        self.assertIn("11/3(화)", weekly[0])
        _, again = self.run_at("2026-11-01T20:10", state)
        self.assertEqual(again, [])

    def test_not_other_days_or_slots(self):
        for now in ("2026-11-01T10:00", "2026-11-02T18:40", "2026-10-31T19:00"):
            _, weekly = self.run_at(now, dict(STARTED))
            self.assertEqual(weekly, [], now)

    def test_nothing_to_tell(self):
        self.assertIsNone(notify.build_weekly({"new": [], "start": [], "close": [], "live": 0}, at(self.SUN).date()))

    def test_more_than_max(self):
        many = [deal(i, first_seen="2026-10-30T09:00:00+09:00") for i in range(notify.WEEKLY_MAX + 3)]
        text = notify.build_weekly(notify.weekly_sections(many, at(self.SUN).date()), at(self.SUN).date())
        self.assertIn("…외 3건은 사이트에서", text)
