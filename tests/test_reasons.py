import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import stock_reasons as reasons
import daily_report as daily


class ReasonTests(unittest.TestCase):
    def test_research_covers_four_time_horizons_and_deduplicates(self):
        search = Mock(return_value=[{'title': '決算', 'url': 'https://example.com', 'published': '2026-10-14'}])
        items = reasons.research_company({'name': 'Example'}, search)
        self.assertEqual(len(items), 1)
        self.assertEqual([c.kwargs['days'] for c in search.call_args_list], [30, 365, 1825, 180])
        self.assertIn('不祥事', search.call_args_list[2].kwargs['keywords'])

    def test_no_key_hypothesis_is_nonempty_and_does_not_invent_incident(self):
        company = {'ticker': 'TEST', 'name': 'Test', 'risks': '原材料、中国需要',
                   'brands': 'TestBrand', 'environment': '日用品需要'}
        with patch.dict('os.environ', {}, clear=True):
            result = reasons.generate_reasons(company, '2026-10-15', [], {'revenueGrowth': -.1})
        self.assertTrue(result['low_reason'].startswith('推測：'))
        self.assertIn('需要', result['low_reason'])
        self.assertIn('日用品需要', result['watch_reason'])
        self.assertNotIn('不祥事', result['low_reason'])
        self.assertNotIn('前日比', result['watch_reason'])

    def test_reviewed_context_is_not_leaked_into_past_or_used_forever(self):
        self.assertEqual(reasons.context_for('9433.T', '2026-10-01'), {})
        self.assertIn('LG CNS', reasons.context_for('9433.T', '2026-10-15')['watch_reason'])
        self.assertEqual(reasons.context_for('9433.T', '2027-01-01'), {})

    def test_detail_preserves_reason_and_sources(self):
        company = {'ticker':'TEST', 'name':'Test', 'business':'製造', 'brands':'製品',
                   'risks':'原材料', 'environment':'需要', '_report_date':'2026-10-15'}
        metric = {'close':100, 'change':1, 'change_pct':1, 'date':'2026-10-14', 'weekly_pct':2}
        with patch.object(daily, 'research_company', return_value=[]), \
             patch.object(daily, 'generate_reasons', return_value={
                 'watch_reason':'新製品の展開に注目', 'low_reason':'推測：原材料高',
                 'sources':[{'title':'発表資料','url':'https://example.com/source','published':'2026-10-14'}]}):
            text = '\n'.join(daily.stock_section(company, metric, 'JP', False))
        self.assertIn('**注目理由：** 新製品の展開に注目', text)
        self.assertIn('https://example.com/source', text)
