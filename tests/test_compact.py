"""Тесты компактного хранения корпуса сигналов."""

import unittest

from trendwatcher.enrichment.tag_filter import SIGNAL_TAGS
from trendwatcher.ingestion.compact import (
    SUMMARY_CAP,
    compact_summary,
    has_signal_tag,
    signal_tags_only,
)


class TestCompact(unittest.TestCase):
    def test_summary_cap(self):
        long = "x" * (SUMMARY_CAP + 50)
        out = compact_summary(long)
        self.assertLessEqual(len(out), SUMMARY_CAP)
        self.assertTrue(out.endswith("…"))

    def test_signal_tags_only(self):
        tags = ["jailbreak", "open_weights", "prompt_injection", "fake"]
        self.assertEqual(
            signal_tags_only(tags),
            ["jailbreak", "prompt_injection"],
        )
        self.assertTrue(has_signal_tag(tags))
        self.assertFalse(has_signal_tag(["open_weights"]))
        self.assertTrue(SIGNAL_TAGS)


if __name__ == "__main__":
    unittest.main()
