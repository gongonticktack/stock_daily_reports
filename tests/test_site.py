import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_site as site


class SiteTests(unittest.TestCase):
    def test_bilingual_toggle_and_language_memory(self):
        page = site.shell('STOCK NEWS', '<p>News</p>')
        self.assertIn('data-set-lang="ja"', page)
        self.assertIn('data-set-lang="en"', page)
        self.assertIn("localStorage.setItem('stock_news_language'", page)
        self.assertIn('STOCK <b>NEWS</b>', page)

    def test_translation_failure_keeps_original_with_warning(self):
        translator = site.Translator(cache={}, limit=0)
        page = site.render_report('# 株式日報\n\n株価は確認できた終値です。', '2026-10-12', translator)
        self.assertIn('株価は確認できた終値です。', page)
        self.assertIn('一部の英訳を取得できませんでした', page)
        self.assertIn('report-content lang-ja', page)
        self.assertIn('report-content lang-en', page)

    def test_market_cards_reuse_real_figures(self):
        report = (
            '## 日本株｜前営業日の注目変動 3銘柄\n\n'
            '### トヨタ自動車｜7203.T\n'
            '[株価・5年チャート](https://example.com)\n\n'
            '**直近終値：3,200.0円｜前日比：+25.0円（+0.79%）**\n\n'
            '**事業概要（登録情報）：** 自動車製造\n\n'
            '**事実・注目理由：** 前日比+0.79%。\n\n'
        )
        cards = site.extract_market_cards(report)
        self.assertEqual(cards[0][2][0]['ticker'], '7203.T')
        self.assertIn('3,200.0円', cards[0][2][0]['price'])
        page = site.market_digest(report, '2026-10-12', site.Translator(cache={}, limit=0))
        self.assertIn('7203.T', page)
        self.assertIn('3,200.0円', page)
        self.assertIn('自動車製造', page)

    def test_numeric_mismatch_rejected(self):
        class BadTranslator:
            def translate(self, value):
                return 'Stock price is 9,999 yen'  # corrupts the source number
        translator = site.Translator(cache={}, limit=2)
        translator.google = BadTranslator()
        translator.backup = BadTranslator()
        self.assertEqual(translator.translate('株価は3,200円'), '株価は3,200円')
        self.assertEqual(translator.untranslated, 1)

    def test_html_escapes(self):
        page = site.bilingual('<script>危険</script>', 'Safe')
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)


if __name__ == '__main__':
    unittest.main()
