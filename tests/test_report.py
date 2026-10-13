import unittest
from datetime import date
import pandas as pd
from scripts.daily_report import metrics, recent_symbols, financial_score, fmt_delta, range_graph

class DailyReportTest(unittest.TestCase):
    def test_metrics_and_range(self):
        idx = pd.date_range('2026-09-28', periods=10, freq='B')
        df = pd.DataFrame({'Open':[100+i for i in range(10)],
                           'High':[105+i for i in range(10)],
                           'Low':[95+i for i in range(10)],
                           'Close':[100+i for i in range(10)]},index=idx)
        m = metrics(df,date(2026,10,11))
        self.assertEqual(m['close'],109)
        self.assertEqual(m['date'],'2026-10-09')
        self.assertAlmostEqual(m['change_pct'],100/108)
        self.assertIn('高値',range_graph(m))

    def test_historical_selection_does_not_use_current_fundamentals(self):
        from unittest.mock import patch
        from scripts import daily_report as report
        universe = [{'ticker': str(i), 'market': market} for market in ('JP','US') for i in range(8)]
        stats = {str(i): {'change_pct': i, 'position5': i, 'bar_count': 1200, 'weekly_pct': None} for i in range(8)}
        with patch.object(report, 'fundamentals', side_effect=AssertionError('Current fundamentals must not be used')):
            selected = report.choose(universe, stats, set(), date(2026,10,1), historical=True)
        self.assertEqual(len(selected['JP']['lows']), 3)
        self.assertEqual(len(selected['US']['lows']), 3)

    def test_historical_window_excludes_same_day_close_and_old_prices(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
        import backfill
        frame = pd.DataFrame({'Close': [1,2,3,4]}, index=pd.to_datetime(
            ['2021-09-30','2021-10-01','2026-09-30','2026-10-01']))
        selected = backfill.price_window(frame, date(2026,10,1))
        self.assertEqual(selected['Close'].tolist(), [2,3])

    def test_recent(self):
        h = {'2026-09-25':['OLD'], '2026-10-01':['RECENT'], '2026-10-11':['TODAY']}
        self.assertEqual(recent_symbols(h,date(2026,10,11)),{'RECENT'})
    def test_fundamental_guard(self):
        self.assertIsNone(financial_score({'revenueGrowth':0.2}))
        self.assertIsNotNone(financial_score({'revenueGrowth':0.2,'freeCashflow':1e9}))
    def test_delta_format(self):
        self.assertEqual(fmt_delta(-1.23,-2.34,'US'),'-1.23ドル（-2.34%）')

if __name__ == '__main__':
    unittest.main()