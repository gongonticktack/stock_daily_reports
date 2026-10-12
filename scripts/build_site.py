#!/usr/bin/env python3
"""Build bilingual stock news pages from archived Japanese reports.

Never alters stock data, numbers, source URLs, or original Japanese markdown.
English translations are best-effort and cached. On failure show Japanese original.
"""
from __future__ import annotations

import html
import hashlib
import json
import logging
import os
import re
import time
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
    def __init__(self, cache=None, limit=40):
        self.cache = cache if cache is not None else load_cache()
        self.limit = limit
        self.calls = 0
        self.failures = 0
        self.google = None
        self.backup = None
        self.untranslated = 0
        self.deadline = time.monotonic() + 55

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
        if self.calls >= self.limit or self.failures >= 4 or time.monotonic() > self.deadline:
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
        # Reject translations that change financial figures, percentages or dates.
        numeric = re.compile(r'(?<!\w)[+-]?\d[\d,]*(?:\.\d+)?%?')
        original_numbers = sorted(numeric.findall(clean))
        translated_numbers = sorted(numeric.findall(translated))
        if translated and not JAPANESE.search(translated) and original_numbers == translated_numbers:
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
  function scrollToStock() {
    const id = location.hash.slice(1);
    if (!id.startsWith('stock-')) return;
    const canonical = id.replace(/-en$/, '');
    const target = document.getElementById(canonical +
      (document.documentElement.lang === 'en' ? '-en' : ''));
    if (target) target.scrollIntoView({block: 'start'});
  }
  function setLanguage(language) {
    const lang = language === 'en' ? 'en' : 'ja';
    document.documentElement.lang = lang;
    buttons.forEach(function(button) {
      button.setAttribute('aria-pressed', String(button.dataset.setLang === lang));
    });
    try { localStorage.setItem('stock_news_language', lang); } catch (e) {}
    requestAnimationFrame(scrollToStock);
  }
  let saved = 'ja';
  try { saved = localStorage.getItem('stock_news_language') || 'ja'; } catch (e) {}
  setLanguage(saved);
  window.addEventListener('hashchange', scrollToStock);
  window.addEventListener('load', scrollToStock);
  buttons.forEach(function(button) {
    button.addEventListener('click', function() { setLanguage(button.dataset.setLang); });
  });
})();
</script>"""


def shell(title, content, *, in_report=False):
    base = '../' if in_report else ''
    stylesheet = DOCS / 'theme.css'
    css_version = hashlib.sha256(stylesheet.read_bytes()).hexdigest()[:12] if stylesheet.exists() else '1'
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="theme-color" content="#0a0919">'
        '<meta name="description" content="Daily Japanese and US stock market reports, available in Japanese and English">'
        '<title>' + esc(title) + '</title>'
        '<link rel="stylesheet" href="' + base + 'theme.css?v=' + css_version + '"></head><body>'
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
        ) + '<div><a class="sister-site" href="https://gongonticktack.github.io/it_news/">' +
        bilingual('IT NEWS を読む ↗', 'Visit IT NEWS ↗') +
        '</a></div></footer></main>' + lang_script() + '</body></html>'
    )


def date_navigation(day, days, *, base='', folder='summary/'):
    ordered = sorted(set(days))
    if day not in ordered:
        return ''
    index = ordered.index(day)
    def button(target, ja, en, relation):
        label = bilingual(ja, en)
        if target is None:
            return '<span class="date-button" aria-disabled="true">' + label + '</span>'
        return ('<a class="date-button" rel="' + relation + '" href="' + base + folder +
                esc(target) + '.html" title="' + esc(target) + '">' + label + '</a>')
    return ('<nav class="date-navigation" aria-label="日付移動 / Browse dates">' +
            button(ordered[index - 1] if index else None, '← 前日', '← Previous', 'prev') +
            '<time datetime="' + esc(day) + '">' + esc(day) + '</time>' +
            button(ordered[index + 1] if index + 1 < len(ordered) else None,
                   '翌日 →', 'Next →', 'next') + '</nav>')


def render_report(markdown_text, day, translator, days=None):
    ja_html = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
    soup = BeautifulSoup(ja_html, 'html.parser')
    anchors = iter(card['anchor'] for _, _, cards in extract_market_cards(markdown_text)
                   for card in cards)
    market_section = False
    for heading in soup.find_all(['h2', 'h3']):
        if heading.name == 'h2':
            market_section = bool(re.match(r'^(日本株|米国株)｜', heading.get_text()))
        elif market_section and '｜' in heading.get_text():
            heading['id'] = next(anchors)
    ja_html = str(soup)
    before = translator.untranslated
    en_html = translator.html(ja_html)
    en_soup = BeautifulSoup(en_html, 'html.parser')
    for heading in en_soup.select('h3[id]'):
        heading['id'] += '-en'
    en_html = str(en_soup)
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
    navigation = date_navigation(day, days or [day], base='../', folder='reports/')
    return shell('STOCK NEWS｜' + day, navigation + hero + notice + body, in_report=True)


def extract_market_cards(report):
    """Extract real stock picks and prices from the archived markdown."""
    groups = []
    occurrences = {}
    sections = re.finditer(r'(?ms)^## (日本株|米国株)｜([^\n]+)\n(.*?)(?=^## |\Z)', report)
    for section in sections:
        market, label, body = section.groups()
        cards = []
        for match in re.finditer(r'(?ms)^### ([^\n]+)\n(.*?)(?=^### |^## |\Z)', body):
            heading, detail = match.groups()
            if '｜' not in heading:
                continue
            name, ticker = heading.rsplit('｜', 1)
            # Independent of translated names, card ordering and report date.
            identity = json.dumps([market.strip(), label.strip(), ticker.strip()], ensure_ascii=False)
            occurrences[identity] = occurrences.get(identity, 0) + 1
            anchor = 'stock-' + ('jp' if market == '日本株' else 'us') + '-' + hashlib.sha256(
                identity.encode('utf-8')).hexdigest()[:24] + '-' + str(occurrences[identity])
            price = re.search(r'\*\*直近終値：([^\n*]+)\*\*', detail)
            business = re.search(r'\*\*事業概要（登録情報）：\*\*\s*([^\n]+)', detail)
            reason = re.search(r'\*\*事実・注目理由：\*\*\s*([^\n]+)', detail)
            range_match = re.search(r'5年高値：([^／\n*]+)／5年安値：([^／\n*]+)／現在のレンジ位置：([0-9]+(?:\.[0-9]+)?)%', detail)
            price_range = None
            if range_match:
                high, low, position = range_match.groups()
                number = lambda value: float(re.search(r'[0-9][0-9,]*(?:\.[0-9]+)?', value).group().replace(',', ''))
                try:
                    if number(high) > number(low) and 0 <= float(position) <= 100:
                        price_range = {'high': high.strip(), 'low': low.strip(), 'position': float(position)}
                except (AttributeError, ValueError):
                    pass
            cards.append({
                'name': name.strip(), 'ticker': ticker.strip(),
                'anchor': anchor,
                'price_range': price_range,
                'price': price.group(1).strip() if price else '',
                'business': business.group(1).strip() if business else '',
                'reason': reason.group(1).strip() if reason else '',
            })
        if cards:
            groups.append((market, label, cards))
    return groups



def range_diagram(price_range):
    """A price range indicator, not a historical time-series chart."""
    if not price_range:
        return ('<div class="range-unavailable">' +
                bilingual('5年レンジ：データ未取得', 'Five-year range: data unavailable') + '</div>')
    position = price_range['position']
    def price(value):
        return bilingual(value, value.replace('円', ' JPY').replace('ドル', ' USD'))
    return ('<figure class="five-year-range"><figcaption>' +
            bilingual('5年レンジの現在位置', 'Position in five-year range') +
            '<strong>' + bilingual(f'安値から {position:.1f}%', f'{position:.1f}% from the low') +
            '</strong></figcaption><div class="range-current">' +
            bilingual('● 現在の終値', '● Latest close') +
            '</div><div class="range-track" role="img" aria-label="' +
            esc(f'安値 0%、高値 100%、現在 {position:.1f}% / Low 0%, high 100%, current {position:.1f}%') +
            '"><span class="range-fill" style="width:' + f'{position:.1f}' +
            '%"></span><span class="range-marker" style="left:' + f'{position:.1f}' +
            '%"></span></div><div class="range-endpoints"><div>' +
            bilingual('5年安値 · 0%', 'Five-year low · 0%') + '<strong>' +
            price(price_range['low']) + '</strong></div><div>' +
            bilingual('5年高値 · 100%', 'Five-year high · 100%') + '<strong>' +
            price(price_range['high']) + '</strong></div></div></figure>')


def market_digest(report, day, translator, *, base=''):
    groups = extract_market_cards(report)
    if not groups:
        return ('<section class="story"><p>' +
                bilingual('最新レポートで銘柄情報をご確認ください。',
                          'Open the latest report for stock details.') +
                '</p><a class="link" href="' + base + 'reports/' + esc(day) + '.html">' +
                bilingual('レポートを開く ↗', 'Open report ↗') + '</a></section>')
    out = '<div class="section-title"><h2>' + bilingual(
        day + ' の注目銘柄', 'Stocks to Watch — ' + day) + '</h2></div>'
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
                    + (range_diagram(card['price_range']) if low else '') +
                    '<p>' + bilingual(card['business'], business_en) + '</p>'
                    '<p class="why"><strong>' + bilingual('注目理由：', 'Why it matters: ') +
                    '</strong>' + bilingual(card['reason'], reason_en) + '</p>'
                    '<a class="link" href="' + base + 'reports/' + esc(day) + '.html#' + card['anchor'] + '">' +
                    bilingual('詳しい分析を見る ↗', 'Full analysis ↗') + '</a></article>')
        out += '</section>'
    return out


def render_index(days, translator, *, day=None, in_summary=False):
    latest = day or (days[0] if days else None)
    base = '../' if in_summary else ''
    hero = ('<section class="hero"><div class="eyebrow">YOUR DAILY MARKET SIGNAL</div>'
            '<h1 class="gradient-text">STOCK NEWS.</h1><p>' +
            bilingual('日本株・米国株の値動き、5年安値圏、注目ニュースを毎朝チェック。',
                      'Track Japanese and US stocks, five-year lows, and market-moving news each morning.') +
            ('<span class="edition">' + bilingual('対象日：', 'Edition: ') + esc(latest) + '</span>' if latest else '') +
            '</p></section>')
    cards = '' if latest else '<section class="story">' + bilingual('レポートの公開を準備しています。', 'Preparing the first report.') + '</section>'
    archive = ('<section class="archive" id="archive"><h2>ARCHIVE / ' +
               bilingual('過去の記事', 'Previous editions') + '</h2><ul>' +
               ''.join('<li><a href="' + base + 'summary/' + esc(date) + '.html">' +
                       bilingual(date + ' のサマリ', 'Summary — ' + date) +
                       '</a></li>' for date in days) + '</ul></section>')
    latest_digest = ''
    notice = ''
    if latest:
        latest_path = ROOT / 'reports' / (latest + '.md')
        before = translator.untranslated
        latest_digest = market_digest(latest_path.read_text(encoding='utf-8'), latest, translator, base=base)
        if translator.untranslated > before:
            notice = ('<p class="translation-note">' + bilingual(
                '一部の英訳を取得できませんでした。該当箇所は日本語の原文を表示しています。',
                'Some passages could not be translated; original Japanese text is shown.'
            ) + '</p>')
    title = 'STOCK NEWS｜' + (latest or '日本株・米国株の日報')
    navigation = date_navigation(latest, days, base=base) if latest else ''
    return shell(title, navigation + hero + notice + latest_digest + cards + archive, in_report=in_summary)


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / 'reports').mkdir(parents=True, exist_ok=True)
    (DOCS / 'summary').mkdir(parents=True, exist_ok=True)
    reports = sorted((ROOT / 'reports').glob('????-??-??.md'), reverse=True)
    days = [p.stem for p in reports]
    translator = Translator(limit=int(os.getenv('TRANSLATION_REQUEST_LIMIT', '40')))
    for path in reports:
        source = path.read_text(encoding='utf-8')
        page = render_report(source, path.stem, translator, days)
        (DOCS / 'reports' / (path.stem + '.html')).write_text(page, encoding='utf-8')
    for day in days:
        (DOCS / 'summary' / (day + '.html')).write_text(
            render_index(days, translator, day=day, in_summary=True), encoding='utf-8')
    (DOCS / 'index.html').write_text(render_index(days, translator), encoding='utf-8')
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(translator.cache, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'STOCK NEWS: {len(reports)} bilingual reports; '
          f'{translator.calls} translation requests; {translator.untranslated} untranslated passages')


if __name__ == '__main__':
    main()
