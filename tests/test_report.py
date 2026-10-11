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