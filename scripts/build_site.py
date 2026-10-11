#!/usr/bin/env python3
"""Build bilingual stock news pages from archived Japanese reports.

Never alters stock data, numbers, source URLs, or original Japanese markdown.
English translations are best-effort and cached. On failure show Japanese original.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
CACHE_PATH = ROOT / 'data' / 'translations_en.json'
LOG = logging.getLogger('stock-site')

DIRECT = {
    '株式日報': 'Stock Daily Report',
    '日本株': 'Japanese Stocks',
    '米国株': 'US Stocks',
    '市場指数（直近取得値）': 'Market Indices (Latest Available)',
    '市場関連ニュース（見出し・公開日時を参照）': 'Market News (Headlines and Publication Dates)',
    '前営業日の注目変動': 'Notable Moves from Previous Session',
    '今週の注目候補': 'Stocks to Watch This Week',
    '週間レビュー': 'Weekly Review',
    '日経平均': 'Nikkei 225',
    'TOPIX': 'TOPIX',
    'NASDAQ総合': 'NASDAQ Composite',
    'NYダウ': 'Dow Jones Industrial Average',
    '最終取引日': 'Last Trading Day',
    '終値': 'Closing Price',
    '前日比': 'Daily Change',
    '指数': 'Index',
    '取引日': 'Trading Date',
    '事業概要（登録情報）': 'Business Overview (Registered Information)',
    '主要ブランド・サービス（登録情報）': 'Major Brands and Services (Registered Information)',
    '主要リスク（登録情報）': 'Key Risks (Registered Information)',
    '事業環境': 'Business Environment',
    '事実・注目理由': 'Facts and Reasons to Watch',
    '予想・確認点': 'Outlook and Items to Verify',
    '関連報道の見出し（直接の株価変動要因とは限りません）': 'Related Headlines (Not Necessarily the Cause of Price Moves)',
    '株価・5年チャート': 'Price and Five-Year Chart',
    '直近終値': 'Latest Closing Price',
    '現地市場の通常取引終値': 'Regular Session Close in the Local Market',
    '日本時間の生成日': 'Generated Date (Japan Time)',
    '業績・財務（取得値）': 'Financial Performance (Reported Data)',
    '5年高値': 'Five-Year High',
    '5年安値': 'Five-Year Low',
    '現在のレンジ位置': 'Position in Five-Year Range',
    '未算出': 'Not Calculated',
    '取得可能な候補がありませんでした。': 'No eligible stocks were available.',
    'ニュースの取得に失敗しました。': 'Could not retrieve the news feed.',
    '投資助言ではありません。': 'This is not investment advice.',
}
JAPANESE = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')


def esc(value):
    return html.escape(str(value), quote=True)


def bilingual(ja, en):
    return '<span class="lang-ja">' + esc(ja) + '</span><span class="lang-en">' + esc(en) + '</span>'


def load_cache():
    try:
        data = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class Translator:
    def __init__(self, cache=None, limit=100):
        self.cache = cache if cache is not None else load_cache()
        self.limit = limit
        self.calls = 0
        self.failures = 0
        self.google = None
        self.backup = None
        self.untranslated = 0

    def translate(self, text):
        if not JAPANESE.search(text):
            return text
        clean = text.strip()
        if not clean:
            return text
        if clean in DIRECT:
            return text.replace(clean, DIRECT[clean])
        if clean in self.cache:
            return text.replace(clean, self.cache[clean])
        if self.calls >= self.limit or self.failures >= 4:
            self.untranslated += 1
            return text
        self.calls += 1
        translated = ''
        try:
            if self.google is None:
                from deep_translator import GoogleTranslator
                self.google = GoogleTranslator(source='auto', target='en')
            translated = self.google.translate(clean[:4500]) or ''
        except Exception as exc:
            LOG.warning('English translation failed: %s', str(exc)[:150])
        if not translated or JAPANESE.search(translated):
            try:
                if self.backup is None:
                    from deep_translator import MyMemoryTranslator
                    self.backup = MyMemoryTranslator(source='japanese', target='english')
                translated = self.backup.translate(clean[:450]) or ''
            except Exception as exc:
                LOG.warning('Backup translation failed: %s', str(exc)[:150])
        if translated and not JAPANESE.search(translated):
            self.cache[clean] = translated
            self.failures = 0
            return text.replace(clean, translated)
        self.failures += 1
        self.untranslated += 1
        return text

    def html(self, source):
        soup = BeautifulSoup(source, 'html.parser')
        for node in list(soup.descendants):
            if not isinstance(node, NavigableString):
                continue
            if node.parent and node.parent.name in ('code', 'pre', 'script', 'style'):
                continue
            text = str(node)
            if JAPANESE.search(text):
                node.replace_with(self.translate(text))
        return str(soup)


def lang_script():
    return """<script>
(function () {
  const buttons = Array.from(document.querySelectorAll('[data-set-lang]'));
  function setLanguage(language) {
    const lang = language === 'en' ? 'en' : 'ja';
    document.documentElement.lang = lang;
    buttons.forEach(function(button) {
      button.setAttribute('aria-pressed', String(button.dataset.setLang === lang));
    });
    try { localStorage.setItem('stock_news_language', lang); } catch (e) {}
  }
  let saved = 'ja';
  try { saved = localStorage.getItem('stock_news_language') || 'ja'; } catch (e) {}
  setLanguage(saved);
  buttons.forEach(function(button) {
    button.addEventListener('click', function() { setLanguage(button.dataset.setLang); });
  });
})();
</script>"""


def shell(title, content, *, in_report=False):
    base = '../' if in_report else ''
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="theme-color" content="#0a0919">'
        '<meta name="description" content="Daily Japanese and US stock market reports, available in Japanese and English">'
        '<title>' + esc(title) + '</title>'
        '<link rel="stylesheet" href="' + base + 'theme.css"></head><body>'
        '<header><div class="top">'
        '<a class="brand" href="' + base + 'index.html">STOCK <b>NEWS</b></a>'
        '<nav><a href="' + base + 'index.html">' + bilingual('最新号', 'Latest') + '</a>'
        '<a href="' + base + 'index.html#archive">' + bilingual('過去の記事', 'Archive') + '</a></nav>'
        '<div class="lang-switch" role="group" aria-label="Language / 表示言語">'
        '<button type="button" data-set-lang="ja" aria-pressed="true" lang="ja">日本語</button>'
        '<button type="button" data-set-lang="en" aria-pressed="false" lang="en">EN</button>'
        '</div></div></header>'
        '<main class="wrap">' + content +
        '<footer>' + bilingual(
            '株価・ニュースの取得日時をご確認ください。情報提供を目的とし、投資助言ではありません。',
            'Check the source dates for prices and news. For information only; not investment advice.'
        ) + '</footer></main>' + lang_script() + '</body></html>'
    )


def render_report(markdown_text, day, translator):
    ja_html = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
    before = translator.untranslated
    en_html = translator.html(ja_html)
    incomplete = translator.untranslated > before
    notice = ('<p class="translation-note">' +
              bilingual('一部の英訳を取得できませんでした。該当箇所は日本語の原文を表示しています。',
                        'Some passages could not be translated and are shown in their original Japanese.') +
              '</p>') if incomplete else ''
    hero = ('<section class="hero"><div class="eyebrow">DAILY MARKET INTELLIGENCE</div>'
            '<h1 class="gradient-text">STOCK NEWS.</h1><p>' + esc(day) + ' ｜ ' +
            bilingual('日本株・米国株の日刊マーケットレポート',
                      'Daily Japanese and US market briefing') + '</p></section>')
    body = ('<section class="glass stock-report">'
            '<div class="report-content lang-ja">' + ja_html + '</div>'
            '<div class="report-content lang-en">' + en_html + '</div>'
            '</section>')
    return shell('STOCK NEWS｜' + day, hero + notice + body, in_report=True)


def extract_market_cards(report):
    """Extract real stock picks and prices from the archived markdown."""
    groups = []
    sections = re.finditer(r'(?ms)^## (日本株|米国株)｜([^\n]+)\n(.*?)(?=^## |\Z)', report)
    for section in sections:
        market, label, body = section.groups()
        cards = []
        for match in re.finditer(r'(?ms)^### ([^\n]+)\n(.*?)(?=^### |^## |\Z)', body):
            heading, detail = match.groups()
            if '｜' not in heading:
                continue
            name, ticker = heading.rsplit('｜', 1)
            price = re.search(r'\*\*直近終値：([^\n*]+)\*\*', detail)
            business = re.search(r'\*\*事業概要（登録情報）：\*\*\s*([^\n]+)', detail)
            reason = re.search(r'\*\*事実・注目理由：\*\*\s*([^\n]+)', detail)
            cards.append({
                'name': name.strip(), 'ticker': ticker.strip(),
                'price': price.group(1).strip() if price else '',
                'business': business.group(1).strip() if business else '',
                'reason': reason.group(1).strip() if reason else '',
            })
        if cards:
            groups.append((market, label, cards))
    return groups


def market_digest(report, day, translator):
    groups = extract_market_cards(report)
    if not groups:
        return ('<section class="story"><p>' +
                bilingual('最新レポートで銘柄情報をご確認ください。',
                          'Open the latest report for stock details.') +
                '</p><a class="link" href="reports/' + esc(day) + '.html">' +
                bilingual('レポートを開く ↗', 'Open report ↗') + '</a></section>')
    out = '<div class="section-title"><h2>' + bilingual(
        '最新の注目銘柄', 'Latest Stocks to Watch') + '</h2></div>'
    for market, label, cards in groups:
        low = '安値圏' in label
        group_en = ('Five-Year Low Candidates' if low else 'Market Movers / Stocks to Watch')
        out += ('<div class="section-title"><h2>' +
                bilingual(market + '｜' + label, ('Japan' if market == '日本株' else 'US') +
                          ' | ' + group_en) + '</h2></div><section class="news stock-home-cards">')
        for number, card in enumerate(cards, 1):
            name_en = translator.translate(card['name'])
            business_en = translator.translate(card['business']) if card['business'] else ''
            reason_en = translator.translate(card['reason']) if card['reason'] else ''
            out += ('<article class="story"><div class="meta">'
                    '<span class="tag">' + ('JP' if market == '日本株' else 'US') +
                    (' · 5Y LOW' if low else ' · MOVERS') + '</span>'
                    '<span>#' + str(number).zfill(2) + '</span>'
                    '<span>' + esc(card['ticker']) + '</span></div>'
                    '<h2>' + bilingual(card['name'], name_en) + '</h2>'
                    '<p class="stock-price">' + esc(card['price']) + '</p>'
                    '<p>' + bilingual(card['business'], business_en) + '</p>'
                    '<p class="why"><strong>' + bilingual('注目理由：', 'Why it matters: ') +
                    '</strong>' + bilingual(card['reason'], reason_en) + '</p>'
                    '<a class="link" href="reports/' + esc(day) + '.html">' +
                    bilingual('詳しい分析を見る ↗', 'Full analysis ↗') + '</a></article>')
        out += '</section>'
    return out


def render_index(days, translator):
    latest = days[0] if days else None
    hero = ('<section class="hero"><div class="eyebrow">YOUR DAILY MARKET SIGNAL</div>'
            '<h1 class="gradient-text">STOCK NEWS.</h1><p>' +
            bilingual('日本株・米国株の値動き、5年安値圏、注目ニュースを毎朝チェック。',
                      'Track Japanese and US stocks, five-year lows, and market-moving news each morning.') +
            ('<span class="edition">' + bilingual('最新号：', 'Latest edition: ') + esc(latest) + '</span>' if latest else '') +
            '</p></section>')
    cards = ''
    if latest:
        entries = [
            ('JP MARKET', '日本株の注目銘柄', 'Japanese Stocks to Watch',
             '値動きと過去5年の安値圏をチェック', 'Explore market moves and five-year price ranges', '↗'),
            ('US MARKET', '米国株の注目銘柄', 'US Stocks to Watch',
             '米国市場の変動銘柄と財務情報', 'US market movers and financial data', '↗'),
            ('MARKET WATCH', '市場指数とニュース', 'Indices and Market News',
             '日経平均・S&P 500などをまとめて確認', 'Follow the Nikkei, S&P 500, and more', '◈'),
            ('ARCHIVE', '過去の日報', 'Previous Reports',
             '日付別に保存したレポートを振り返る', 'Browse the daily report archive', '◷'),
        ]
        cards = '<section class="news stock-home-cards">'
        for index, (tag, ja_title, en_title, ja_text, en_text, icon) in enumerate(entries):
            target = '#archive' if index == 3 else 'reports/' + esc(latest) + '.html'
            cards += ('<article class="story"><div class="meta"><span class="tag">' + tag +
                      '</span></div><div class="feature-icon">' + icon + '</div>'
                      '<h2>' + bilingual(ja_title, en_title) + '</h2>'
                      '<p>' + bilingual(ja_text, en_text) + '</p>'
                      '<a class="link" href="' + target + '">' +
                      bilingual('詳しく見る ↗', 'Read report ↗') + '</a></article>')
        cards += '</section>'
    else:
        cards = '<section class="story">' + bilingual('レポートの公開を準備しています。', 'Preparing the first report.') + '</section>'
    archive = ('<section class="archive" id="archive"><h2>ARCHIVE / ' +
               bilingual('過去の記事', 'Previous editions') + '</h2><ul>' +
               ''.join('<li><a href="reports/' + esc(day) + '.html">' +
                       bilingual(day + ' の株式日報', 'Stock report — ' + day) +
                       '</a></li>' for day in days) + '</ul></section>')
    latest_digest = ''
    if latest:
        latest_path = ROOT / 'reports' / (latest + '.md')
        latest_digest = market_digest(latest_path.read_text(encoding='utf-8'), latest, translator)
    return shell('STOCK NEWS｜日本株・米国株の日報', hero + latest_digest + cards + archive)


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / 'reports').mkdir(parents=True, exist_ok=True)
    reports = sorted((ROOT / 'reports').glob('????-??-??.md'), reverse=True)
    translator = Translator(limit=int(os.getenv('TRANSLATION_REQUEST_LIMIT', '100')))
    for path in reports:
        source = path.read_text(encoding='utf-8')
        page = render_report(source, path.stem, translator)
        (DOCS / 'reports' / (path.stem + '.html')).write_text(page, encoding='utf-8')
    (DOCS / 'index.html').write_text(render_index([p.stem for p in reports], translator), encoding='utf-8')
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(translator.cache, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'STOCK NEWS: {len(reports)} bilingual reports; '
          f'{translator.calls} translation requests; {translator.untranslated} untranslated passages')


if __name__ == '__main__':
    main()
