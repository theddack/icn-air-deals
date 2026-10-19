"""Secret Flying 서울 출발 특가. 제목은 2026-10-19 서울 특가 목록에 실제로 올라온 공개 게시물 제목이다."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from collector import secretflying as sf


def card(title, url):
    return (f'<article class="post type-post category-seoul"><div class="card"><div class="entry-block">'
            f'<h3 class="entry-title"><a class="title-link" target="_blank" href="{url}">{title}</a></h3></div></div></article>')


LOCKED = '<article class="post"><div class="locked-deal-card"><a class="locked-link" href="#"><p>Premium</p></a></div></article>'
PAGE = (card("Seoul, South Korea to Vienna, Austria for only $442 USD roundtrip", "https://www.secretflying.com/posts/a/")
        + LOCKED
        + card("Seoul, South Korea to Vienna, Austria for only $222 USD one-way", "https://www.secretflying.com/posts/b/")
        + card("SUMMER: Non-stop from Seattle to Seoul, South Korea for only $335 roundtrip", "https://www.secretflying.com/posts/c/"))


class TestParse(unittest.TestCase):
    def test_title(self):
        d = sf.parse_title("XMAS &amp; NEW YEAR: Non-stop from Seoul, South Korea to Venice, Italy for only $417 USD roundtrip".replace("&amp;", "&"))
        self.assertEqual((d["destination"], d["price"], d["currency"], d["trip"], d["nonstop"], d["tag"]),
                         ("Venice, Italy", 417, "USD", "roundtrip", True, "XMAS & NEW YEAR"))
        self.assertEqual(sf.parse_title("Seoul, South Korea to Da Nang, Vietnam for only $153 USD roundtrip")["price"], 153)

    def test_only_seoul_departures(self):
        self.assertIsNone(sf.parse_title("SUMMER: Non-stop from Seattle to Seoul, South Korea for only $335 roundtrip"))
        self.assertIsNone(sf.parse_title("Tokyo, Japan to Vancouver, Canada for only $478 USD roundtrip"))

    def test_page_skips_locked_and_other_origins(self):
        items = sf.parse(PAGE)
        self.assertEqual([(i["url"][-2:], i["trip"]) for i in items], [("a/", "roundtrip"), ("b/", "oneway")])


class TestMerge(unittest.TestCase):
    def test_keeps_first_seen_and_drops_stale(self):
        prev = [{"url": "u1", "first_seen": "2026-10-10", "last_seen": "2026-10-18"},
                {"url": "old", "first_seen": "2026-09-20", "last_seen": "2026-10-01"}]
        out = sf.merge(prev, [{"url": "u1", "title": "t"}, {"url": "u2", "title": "t2"}], date(2026, 10, 19))
        by = {d["url"]: d for d in out}
        self.assertEqual(set(by), {"u1", "u2"})
        self.assertEqual((by["u1"]["first_seen"], by["u1"]["last_seen"]), ("2026-10-10", "2026-10-19"))
        self.assertEqual(by["u2"]["first_seen"], "2026-10-19")


class TestMain(unittest.TestCase):
    def test_once_a_day_and_failure_keeps_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "secretflying.json"
            with mock.patch.object(sf, "OUT", out), mock.patch.object(sf, "fetch", return_value=PAGE) as f:
                self.assertEqual(sf.main(date(2026, 10, 19)), 0)
                self.assertEqual(sf.main(date(2026, 10, 19)), 0)  # 같은 날 두 번째는 받지 않는다
                self.assertEqual(f.call_count, 1)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual((saved["fetched_on"], len(saved["deals"])), ("2026-10-19", 2))
            with mock.patch.object(sf, "OUT", out), mock.patch.object(sf, "fetch", side_effect=OSError("down")):
                self.assertEqual(sf.main(date(2026, 10, 20)), 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), saved)


if __name__ == "__main__":
    unittest.main()
