import unittest

import numpy as np

from tools.report.flux_patterns import build_flux_pattern_summary


class TestFluxPatterns(unittest.TestCase):
    def test_build_flux_pattern_summary_classifies_unusual_days(self):
        timestamps = []
        net_flux = []
        start = 1_700_000_000_000
        for day in range(6):
            for step in range(24 * 12):
                ts = start + day * 86_400_000 + step * 300_000
                hour = (step // 12) % 24
                base = np.sin(hour / 24 * np.pi * 2.0)
                if day == 5 and 12 <= hour <= 17:
                    base += 3.0
                timestamps.append(ts)
                net_flux.append(base)

        summary = build_flux_pattern_summary(np.asarray(net_flux), np.asarray(timestamps))
        self.assertTrue(summary['available'])
        self.assertEqual(summary['n_days'], 6)
        self.assertEqual(len(summary['typical_day_summary']['median']), 24)
        self.assertEqual(len(summary['unusual_day_summary']['median']), 24)
        self.assertIn(summary['daily_rows'][-1]['date'], summary['top_unusual_dates'])
        labels = {row['label'] for row in summary['daily_rows']}
        self.assertIn('typical', labels)
        self.assertIn('unusual', labels)


if __name__ == '__main__':
    unittest.main()
