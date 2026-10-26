"""텔레그램 알림: 처음엔 연결 안내만, 그 뒤로는 새 할인·곧 마감을 한 번씩만 보낸다. 행사는 형식만 흉내 낸 예시다."""

import unittest
from datetime import date

from collector import notify

TODAY = date(2026, 10, 27)


def deal(i, **kw):
    base = {"id": f"d{i}", "section": "flight", "airline": "제주항공", "kind": "domestic", "verification": "news",
            "event_name": f"행사 {i}", "headline": f"제주항공 행사 {i}", "routes": [{"origin": "인천(ICN)", "destination": "오사카(KIX)"}],
            "discount": "최대 30%", "sale_start": "2026-10-20", "sale_end": "2026-11-10", "from_icn": "yes",
            "first_seen": "2026-10-27T07:20:00+09:00", "last_published": "2026-10-26",
            "official_url": "https://www.jejuair.net/", "articles": [{"url": "https://news.example/a"}]}
    return {**base, **kw}


class TestNotify(unittest.TestCase):
    def run_once(self, deals, state, stats=None):
        out = []
        st = notify.run({"deals": deals, "stats": stats or {}}, state, TODAY, out.append)
        return st, out

    def test_first_run_sends_only_hello_and_marks_existing(self):
        st, out = self.run_once([deal(1), deal(2)], {})
        self.assertEqual(len(out), 1)
        self.assertIn("연결됐습니다", out[0])
        st, out = self.run_once([deal(1), deal(2)], st)
        self.assertEqual(out, [])

    def test_new_deal_sent_once(self):
        st, _ = self.run_once([deal(1)], {})
        st, out = self.run_once([deal(1), deal(2)], st)
        self.assertEqual(len(out), 1)
        self.assertIn("새 할인 1건", out[0])
        self.assertIn("<b>오사카</b>", out[0])
        self.assertIn('href="https://www.jejuair.net/"', out[0])
        _, out = self.run_once([deal(1), deal(2)], st)
        self.assertEqual(out, [])

    def test_closing_sent_once_and_skips_ended_old_and_other_origin(self):
        st, _ = self.run_once([deal(1)], {})
        deals = [deal(1, sale_end="2026-10-28"),                 # 내일 마감 → 곧 마감
                 deal(2, sale_end="2026-10-20"),                 # 마감
                 deal(3, first_seen="2026-10-01T07:00:00+09:00"),  # 오래전에 본 행사(id만 바뀜)
                 deal(4, from_icn="no")]                         # 인천 외 출발
        st, out = self.run_once(deals, st)
        self.assertEqual(len(out), 1)
        self.assertIn("곧 마감 1건", out[0])
        self.assertIn("D-1", out[0])
        _, out = self.run_once(deals, st)
        self.assertEqual(out, [])

    def test_text_is_escaped(self):
        st, _ = self.run_once([], {})
        _, out = self.run_once([deal(9, routes=[], event_name="<특가> & 이벤트")], st)
        self.assertIn("&lt;특가&gt; &amp; 이벤트", out[0])

    def test_failed_queries_warned_once_a_day(self):
        st, _ = self.run_once([], {})
        st, out = self.run_once([], st, {"failed_queries": 3})
        self.assertTrue(any("3개가 실패" in m for m in out))
        _, out = self.run_once([], st, {"failed_queries": 3})
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
