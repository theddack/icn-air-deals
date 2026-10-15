"""사람이 정답을 단 실제 기사로 묶기 결과를 검사한다. 항공 123건, 호텔·숙박 63건(2026-09 ~ 10).

- 잘못 합침(서로 다른 행사가 한 묶음): 0건이어야 한다
- 잘못 나눔(한 행사가 여러 묶음): 지금 수준(MAX_SPLITS)보다 나빠지면 실패
"""

import json
import unittest
from collections import defaultdict
from pathlib import Path

from collector.main import enrich
from collector.merge import cluster_articles

FIXTURE = Path(__file__).parent / "fixtures" / "labeled_2026-10-15.json"
MAX_SPLITS = 1  # 2026-10-15 실측: 핀에어 얼리버드 1건이 둘로 나뉨. 줄이면 좋고, 늘면 회귀다.
RULE_ADDITIONS = Path(__file__).parent / "fixtures" / "labeled_rule_additions_2026-10-15.json"
HOTEL_FIXTURE = Path(__file__).parent / "fixtures" / "labeled_hotels_2026-10-15.json"
# 2026-10-15 실측: 숙박세일 페스타가 할인액(최대 7만·9만·5만·3만원)이 달라 4묶음으로 나뉨 = 3
HOTEL_MAX_SPLITS = 3


def load(*fixtures):
    data = {"ambiguous": [], "articles": []}
    for f in fixtures or (FIXTURE,):
        d = json.loads(f.read_text(encoding="utf-8"))
        data["ambiguous"] += d["ambiguous"]
        data["articles"] += d["articles"]
    label_of = {a["url"]: a["label"] for a in data["articles"]}
    ambiguous = {frozenset(p) for p in data["ambiguous"]}
    deals = cluster_articles([enrich({k: a[k] for k in ("title", "outlet", "url", "published", "first_seen")})
                              for a in data["articles"]])
    return deals, label_of, ambiguous


class TestLabeledSample(unittest.TestCase):
    fixtures, max_splits = (FIXTURE,), MAX_SPLITS

    @classmethod
    def setUpClass(cls):
        cls.deals, cls.label_of, cls.ambiguous = load(*cls.fixtures)

    def test_no_wrong_merges(self):
        wrong = []
        for d in self.deals:
            labels = {self.label_of[a["url"]] for a in d["articles"]} - {None}
            for x in labels:
                for y in labels:
                    if x < y and frozenset((x, y)) not in self.ambiguous:
                        wrong.append((d["airline"], x, y))
        self.assertEqual(wrong, [], "서로 다른 행사가 한 묶음에 들어갔다")

    def test_splits_do_not_get_worse(self):
        deals_per_label = defaultdict(set)
        for d in self.deals:
            for a in d["articles"]:
                label = self.label_of[a["url"]]
                if label:
                    deals_per_label[label].add(d["id"])
        splits = {k: len(v) for k, v in deals_per_label.items() if len(v) > 1}
        self.assertLessEqual(sum(n - 1 for n in splits.values()), self.max_splits, splits)

    def test_multi_airline_articles_stay_alone(self):
        for d in self.deals:
            if d["airline_id"] == "multi":
                self.assertEqual(len(d["articles"]), 1)


class TestLabeledWithRuleAdditions(TestLabeledSample):
    """기존 123건 + 2026-10-15 판정 규칙 보완으로 새로 수집되는 12건. 합쳐도 잘못 합침·나눔이 늘면 안 된다."""
    fixtures, max_splits = (FIXTURE, RULE_ADDITIONS), MAX_SPLITS


class TestLabeledHotelSample(TestLabeledSample):
    fixtures, max_splits = (HOTEL_FIXTURE,), HOTEL_MAX_SPLITS

    def test_all_classified_as_hotel(self):
        self.assertEqual({d["section"] for d in self.deals}, {"hotel"})


if __name__ == "__main__":
    unittest.main()
