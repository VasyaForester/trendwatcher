"""Тесты разбиения графиков динамики и масштаба оси Y."""

import unittest

from trendwatcher.analytics.timeseries import _chart_bundle, _nice_axis_max
from trendwatcher.enrichment.tag_filter import (
    SIGNAL_TAGS,
    TREND_CHART_GENERAL,
    TREND_CHART_SPECIAL,
)


class TestChartSplit(unittest.TestCase):
    def test_general_and_special_partition_signals(self):
        self.assertTrue(TREND_CHART_GENERAL.isdisjoint(TREND_CHART_SPECIAL))
        self.assertEqual(TREND_CHART_GENERAL | TREND_CHART_SPECIAL, SIGNAL_TAGS)
        self.assertIn("jailbreak", TREND_CHART_GENERAL)
        self.assertIn("agent_security", TREND_CHART_GENERAL)
        self.assertIn("self_evolving_agents", TREND_CHART_SPECIAL)
        self.assertIn("agent_swarm_security", TREND_CHART_SPECIAL)

    def test_nice_axis_max(self):
        self.assertGreaterEqual(_nice_axis_max(17), 17)
        self.assertGreaterEqual(_nice_axis_max(100), 100)
        self.assertLessEqual(_nice_axis_max(17), 30)

    def test_chart_bundle_scales_independently(self):
        series = {
            "jailbreak": [10, 20, 100],
            "agent_security": [5, 8, 12],
            "self_evolving_agents": [1, 2, 3],
            "agent_swarm_security": [0, 1, 2],
        }
        general = _chart_bundle(series, TREND_CHART_GENERAL)
        special = _chart_bundle(series, TREND_CHART_SPECIAL)
        self.assertIn("jailbreak", general["tags"])
        self.assertIn("self_evolving_agents", special["tags"])
        self.assertGreater(general["y_max"], special["y_max"])


if __name__ == "__main__":
    unittest.main()
