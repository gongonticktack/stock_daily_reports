import sys
import unittest
import tempfile
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_site as site


class SiteTests(unittest.TestCase):
    def test_date_navigation_boundaries_gaps_and_paths(self):
        days = ['2026-10-12', '2026-10-10', '2026-10-08']
        for day, prev, next_day in [('2026-10-08', None, '2026-10-10'),
                                   ('2026-10-10', '2026-10-08', '2026-10-12'),
                                   ('2026-10-12', '2026-10-10', None)]:
            soup = BeautifulSoup(site.date_navigation(day, days, base='../'), 'html.parser')
            self.assertEqual(soup.time['datetime'], day)
            for relation, target in [('prev', prev), ('next', next_day)]:
                link = soup.find('a', rel=relation)
                if target:
                    self.assertEqual(link['href'], '../summary/' + target + '.html')
                else:
                    self.assertIsNone(link)
            self.assertEqual(len(soup.select('[aria-disabled="true"]')), int(prev is None) + int(next_day is None))

    @staticmethod
    def fixture():
        def group(market, label, stocks):
            return '## ' + market + '｜' + label + '\n\n' + ''.join(
                '### ' + name + '｜' + ticker + '\n\n**直近終値：123.45円**\n\n'
                for name, ticker in stocks)
        return (group('日本株', '注目候補', [('同名', 'ABC'), ('同名', 'XYZ'), ('同名', 'ABC')]) +
                group('米国株', '注目候補', [('同名', 'ABC')]) +
                group('日本株', '安値圏', [('同名', 'ABC')]))

    def test_unique_bilingual_anchor_targets_and_stability(self):
        source = self.fixture()
        translator = site.Translator(cache={}, limit=0)
        detail = BeautifulSoup(site.render_report(source, '2026-10-12', translator), 'html.parser')
        ids = [h['id'] for h in detail.select('h3[id]')]
        self.assertEqual(len(ids), 10)
        self.assertEqual(len(ids), len(set(ids)))
        digest = BeautifulSoup(site.market_digest(source, '2026-10-12', translator), 'html.parser')
        for link in digest.select('a.link'):
            anchor = urlsplit(link['href']).fragment
            for suffix in ('', '-en'):
                self.assertEqual(len(detail.select('[id="' + anchor + suffix + '"]')), 1)
        anchors = lambda text: [c['anchor'] for _, _, cards in site.extract_market_cards(text) for c in cards]
        self.assertEqual(anchors(source), anchors(source.replace('同名', '社名変更')))
        reordered = source.replace('### 同名｜XYZ\n\n**直近終値：123.45円**\n\n', '')
        self.assertEqual(anchors(source)[0], anchors(reordered)[0])
        self.assertEqual(anchors(source)[2], anchors(reordered)[1])

    def test_build_daily_summaries_latest_archive_and_rebuild(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'reports').mkdir()
            for day, ticker in [('2026-10-11', 'OLDCO'), ('2026-10-12', 'NEWCO')]:
                (root / 'reports' / (day + '.md')).write_text(
                    '## 日本株｜注目候補\n\n### 同名｜' + ticker + '\n\n**直近終値：123.45円**\n', encoding='utf-8')
            with patch.object(site, 'ROOT', root), patch.object(site, 'DOCS', root / 'docs'), \
                 patch.object(site, 'CACHE_PATH', root / 'data/cache.json'), \
                 patch.dict('os.environ', {'TRANSLATION_REQUEST_LIMIT': '0'}):
                site.main()
                old = (root / 'docs/summary/2026-10-11.html').read_text(encoding='utf-8')
                index = (root / 'docs/index.html').read_text(encoding='utf-8')
                self.assertIn('NEWCO', index)
                self.assertNotIn('OLDCO', index)
                self.assertIn('OLDCO', old)
                self.assertNotIn('NEWCO', old)
                self.assertIn('href="../theme.css?v=', old)
                self.assertIn('href="../index.html"', old)
                self.assertIn('href="summary/2026-10-11.html"', index)
                archive = BeautifulSoup(index, 'html.parser').find(id='archive')
                self.assertEqual(len(archive.select('a')), 2)
                self.assertTrue(all(a['href'].startswith('summary/') for a in archive.select('a')))
                self.assertLess(index.index('class="date-navigation"'), index.index('class="hero"'))
                self.assertIn('href="../reports/2026-10-11.html#stock-', old)
                self.assertIn('translation-note', old)
                for tag in ('JP MARKET', 'US MARKET', 'MARKET WATCH', 'feature-icon'):
                    self.assertNotIn(tag, index)
                for summary in (root / 'docs/summary').glob('*.html'):
                    soup = BeautifulSoup(summary.read_text(encoding='utf-8'), 'html.parser')
                    for link in soup.select('a[href]'):
                        url = urlsplit(link['href'])
                        if url.scheme or url.netloc:
                            continue
                        target = (summary.parent / url.path).resolve()
                        self.assertTrue(target.exists(), link['href'])
                        if url.fragment.startswith('stock-'):
                            detail = BeautifulSoup(target.read_text(encoding='utf-8'), 'html.parser')
                            self.assertIsNotNone(detail.find(id=url.fragment))
                site.main()
                self.assertEqual(old, (root / 'docs/summary/2026-10-11.html').read_text(encoding='utf-8'))


    def test_summary_range_indicator_uses_archived_numbers_and_handles_missing_data(self):
        for position in (0.0, 8.4, 100.0):
            source = ('## 日本株｜過去5年安値圏候補\n\n### 第一三共｜4568.T\n\n'
                      '**直近終値：2,623.0円**\n\n'
                      f'**5年高値：6,257.0円／5年安値：2,288.0円／現在のレンジ位置：{position:.1f}%**\n')
            card = site.extract_market_cards(source)[0][2][0]
            self.assertEqual(card['price_range']['position'], position)
            soup = BeautifulSoup(site.market_digest(source, '2026-10-13',
                                 site.Translator(cache={}, limit=0)), 'html.parser')
            self.assertEqual(soup.select_one('.range-marker')['style'], f'left:{position:.1f}%')
            self.assertIn('2,288.0円', soup.select_one('.range-endpoints').get_text())
            self.assertIn('6,257.0円', soup.select_one('.range-endpoints').get_text())
            self.assertIn(f'{position:.1f}%', soup.select_one('[role="img"]')['aria-label'])
            self.assertIn('Five-year low', soup.get_text())
        for bad in ('', '**5年高値：100円／5年安値：100円／現在のレンジ位置：8.4%**',
                    '**5年高値：200円／5年安値：100円／現在のレンジ位置：101%**'):
            source = '## 日本株｜安値圏\n\n### 候補｜ABC\n\n' + bad
            rendered = site.market_digest(source, '2026-10-13', site.Translator(cache={}, limit=0))
            self.assertIn('データ未取得', rendered)
            self.assertNotIn('range-marker', rendered)
        movers = '## 日本株｜注目候補\n\n### 候補｜ABC\n'
        self.assertNotIn('five-year-range', site.market_digest(movers, '2026-10-13',
                                                             site.Translator(cache={}, limit=0)))

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

    def test_summary_products_reasons_and_evidence(self):
        source = ('## 日本株｜注目候補\n\n### 企業A｜AAA\n'
                  '**主要ブランド・サービス（登録情報）：** 商品A、サービスB\n'
                  '**事実・注目理由：** 前日比+3.0%。\n'
                  '**注目理由：** 決算発表で売上増加を公表。\n'
                  '**関連報道の見出し（直接の株価変動要因とは限りません）：**\n'
                  '- [決算発表](https://example.com/results)（2026-10-15）\n\n'
                  '## 日本株｜安値圏候補\n\n### 企業B｜BBB\n'
                  '**主要ブランド・サービス（登録情報）：** 商品C\n'
                  '**主要リスク（登録情報）：** 原材料費\n'
                  '**事実・注目理由：** 5年レンジ10.0%。\n')
        soup = BeautifulSoup(site.market_digest(source, '2026-10-15',
                             site.Translator(cache={}, limit=0)), 'html.parser')
        mover, low = soup.select('article')
        self.assertIn('商品A、サービスB', mover.select_one('.stock-brands').get_text())
        self.assertIn('注目理由：', mover.select_one('.why').get_text())
        self.assertIn('決算発表で売上増加を公表。', mover.select_one('.why').get_text())
        self.assertIsNone(mover.select_one('.stock-news'))
        self.assertNotIn('https://example.com/results', str(soup))
        self.assertIn('安値の理由：', low.select_one('.why').get_text())
        self.assertIn('推測：', low.select_one('.why').get_text())
        self.assertIn('利益率', low.select_one('.why').get_text())
        self.assertIsNone(low.select_one('.stock-selection'))
        explicit = source.replace('**主要リスク（登録情報）：** 原材料費',
                                  '**安値の理由：** 業績予想を下方修正。')
        self.assertIn('業績予想を下方修正。', site.market_digest(
            explicit, '2026-10-15', site.Translator(cache={}, limit=0)))

    def test_archived_summary_replaces_price_only_reason_with_business_topic(self):
        source = ('## 米国株｜注目候補\n\n### Test Co｜TEST\n'
                  '**事業環境：** データセンター需要\n'
                  '**主要ブランド・サービス（登録情報）：** TestCloud\n'
                  '**事実・注目理由：** 前日比+8.0%、週間+10.0%。\n')
        page = BeautifulSoup(site.market_digest(source, '2026-10-01',
                             site.Translator(cache={}, limit=0)), 'html.parser')
        reason = page.select_one('.why').get_text()
        self.assertIn('データセンター需要', reason)
        self.assertNotIn('8.0%', reason)
        self.assertNotIn('10.0%', reason)

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
