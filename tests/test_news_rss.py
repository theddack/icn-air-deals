import unittest
import urllib.error
from unittest import mock

from collector.sources import news_rss

RSS = b"""<rss><channel><item><title>t - o</title><source>o</source><link>https://n.example/1</link>
<pubDate>Mon, 23 Nov 2026 01:00:00 GMT</pubDate></item></channel></rss>"""


def http_error(code):
    return urllib.error.HTTPError("https://news.google.com/rss", code, "x", {}, None)


class TestRetry429(unittest.TestCase):
    def run_collect(self, plan, qs=("a", "b", "c")):
        """plan: 검색어 → 차례로 낼 결과(예외 또는 RSS). → (items, failed, total, 받은 순서, 쉰 시간)"""
        calls, sleeps = [], []

        def fetch(q, lang="ko"):
            calls.append(q)
            r = plan[q].pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch.object(news_rss, "queries", lambda: [(q, "ko") for q in qs]):
            items, failed, total = news_rss.collect(fetch=fetch, sleep=sleeps.append)
        return items, failed, total, calls, sleeps

    def test_429_waits_and_retries_once_then_slows_down(self):
        items, failed, total, calls, sleeps = self.run_collect(
            {"a": [RSS], "b": [http_error(429), RSS], "c": [RSS]})
        self.assertEqual((len(items), failed, total), (3, 0, 3))
        self.assertEqual(calls, ["a", "b", "b", "c"])
        self.assertEqual(sleeps, [1.0, news_rss.RETRY_WAIT, news_rss.SLOW_DELAY])

    def test_second_429_counts_as_failed(self):
        items, failed, _, calls, _ = self.run_collect({"a": [http_error(429), http_error(429)], "b": [RSS], "c": [RSS]})
        self.assertEqual((len(items), failed), (2, 1))
        self.assertEqual(calls, ["a", "a", "b", "c"])

    def test_other_errors_are_not_retried(self):
        _, failed, _, calls, sleeps = self.run_collect({"a": [http_error(503)], "b": [RSS], "c": [RSS]})
        self.assertEqual(failed, 1)
        self.assertEqual(calls, ["a", "b", "c"])
        self.assertNotIn(news_rss.RETRY_WAIT, sleeps)

    def test_retries_are_capped_per_run(self):
        qs = [f"q{i}" for i in range(news_rss.RETRY_MAX + 2)]
        _, failed, _, calls, sleeps = self.run_collect({q: [http_error(429), http_error(429)] for q in qs}, qs)
        self.assertEqual(sleeps.count(news_rss.RETRY_WAIT), news_rss.RETRY_MAX)
        self.assertEqual(failed, len(qs))
        self.assertEqual(len(calls), len(qs) + news_rss.RETRY_MAX)


if __name__ == "__main__":
    unittest.main()
