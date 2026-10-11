#!/usr/bin/env python3
"""Japanese daily stock report: data-first, no invented quotes or 5y ranges."""
from __future__ import annotations
import html
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import feedparser
import markdown
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
JST = ZoneInfo('Asia/Tokyo')
LOG = logging.getLogger('stock-daily')


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def fmt_price(v, market):
    return f'{v:,.2f}ドル' if market == 'US' else f'{v:,.1f}円'


def fmt_delta(v, pct, market):
    sign = '+' if v >= 0 else '-'
    return f'{sign}{fmt_price(abs(v), market)}（{pct:+.2f}%）'


def escape(s):
    return html.escape(str(s), quote=False).replace('[', r'\[').replace(']', r'\]')


def get_history(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Yahoo daily OHLC; split-adjusted historical OHLC, NOT dividend-adjusted."""
    result = {}
    for i in range(0, len(tickers), 12):
        chunk = tickers[i:i+12]
        for attempt in range(3):
            try:
                raw = yf.download(
                    tickers=chunk, period='5y', interval='1d',
                    auto_adjust=False, actions=False, group_by='ticker',
                    progress=False, threads=False, timeout=35,
                )
                for symbol in chunk:
                    try:
                        frame = raw[symbol] if isinstance(raw.columns, pd.MultiIndex) else raw
                        frame = frame[['Open', 'High', 'Low', 'Close']].dropna(subset=['Close']).copy()
                        frame = frame.loc[(frame['Close'] > 0) & (frame['High'] > 0) & (frame['Low'] > 0)]
                        if len(frame) >= 8:
                            result[symbol] = frame
                    except (KeyError, ValueError, TypeError):
                        LOG.warning('OHLC unavailable for %s', symbol)
                break
            except Exception as exc:
                LOG.warning('download attempt %s for %s: %s', attempt+1, chunk, exc)
                time.sleep(2 * (attempt+1))
        time.sleep(0.4)
    return result


def session_date(ts):
    return pd.Timestamp(ts).date()


def metrics(frame: pd.DataFrame, today: date):
    # Do not use bars dated in the future relative to Japan today.
    frame = frame.loc[[session_date(idx) <= today for idx in frame.index]]
    if len(frame) < 8:
        return None
    close = float(frame['Close'].iloc[-1])
    prev = float(frame['Close'].iloc[-2])
    high = float(frame['High'].max())
    low = float(frame['Low'].min())
    if prev <= 0 or high <= low:
        return None
    last = session_date(frame.index[-1])
    if (today-last).days > 7:
        return None  # stale quote: do not present as latest
    start_of_week = today - timedelta(days=today.weekday())
    before_week = frame.loc[[session_date(idx) < start_of_week for idx in frame.index]]
    weekly = None
    if len(before_week) and last >= start_of_week:
        base = float(before_week['Close'].iloc[-1])
        if base > 0:
            weekly = 100 * (close / base - 1)
    return {
        'close': close, 'prev': prev, 'change': close-prev,
        'change_pct': 100*(close/prev-1),
        'high5': high, 'low5': low,
        'position5': max(0, min(100, 100*(close-low)/(high-low))),
        'date': last.isoformat(), 'weekly_pct': weekly,
        'bar_count': len(frame),
    }


def fundamentals(symbol):
    """Yahoo fundamentals are best-effort; missing values remain missing."""
    try:
        info = yf.Ticker(symbol).info
        keys = ('revenueGrowth', 'operatingMargins', 'totalCash', 'totalDebt',
                'freeCashflow', 'returnOnEquity', 'trailingPE', 'priceToBook')
        values = {k: float(info[k]) for k in keys if isinstance(info.get(k), (float, int))}
        if isinstance(info.get('financialCurrency'), str):
            values['_currency'] = info['financialCurrency']
        return values
    except Exception as exc:
        LOG.warning('fundamentals unavailable for %s: %s', symbol, exc)
        return {}


def financial_score(f):
    """Require both operating performance and financing/cash-flow data."""
    operating = any(k in f for k in ('revenueGrowth', 'operatingMargins'))
    finance = any(k in f for k in ('totalCash', 'totalDebt', 'freeCashflow'))
    if not (operating and finance):
        return None
    penalty = 0.0
    if f.get('operatingMargins', 0) < 0:
        penalty += 15
    if f.get('revenueGrowth', 0) < -0.05:
        penalty += 8
    if f.get('freeCashflow', 0) < 0:
        penalty += 7
    if 'totalDebt' in f and 'totalCash' in f and f['totalDebt'] > 3*max(f['totalCash'], 1):
        penalty += 6
    return penalty


def news_search(term, days=7, limit=2):
    # News titles are shown as attributed headlines, NOT independently verified events.
    query = quote(f'"{term}" when:{days}d')
    url = f'https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja'
    try:
        r = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0 (stock-report-bot)'})
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        items = []
        for e in feed.entries[:limit]:
            published = e.get('published', '')
            items.append({'title': e.get('title', ''), 'url': e.get('link', ''), 'published': published})
        return items
    except Exception as exc:
        LOG.warning('news unavailable for %s: %s', term, exc)
        return []


def quote_link(symbol, market):
    if market == 'JP':
        return f'https://finance.yahoo.co.jp/quote/{symbol}/chart'
    return f'https://finance.yahoo.com/quote/{symbol}/chart/'


def range_graph(m):
    # A range diagram, NOT a time-series chart. Highest price at top.
    slot = min(10, max(0, round((100-m['position5'])/10)))
    lines = [f"高値 {m['high5']:,.2f} ┐"]
    for i in range(11):
        lines.append('             ● 現在' if i == slot else '             │')
    lines.append(f"安値 {m['low5']:,.2f} ┘")
    return '\n'.join(lines)


def describe_financials(f, market):
    if not f:
        return '業績・財務データは取得できませんでした。評価保留。'
    out = []
    if 'revenueGrowth' in f:
        out.append(f"売上成長率 {f['revenueGrowth']*100:+.1f}%")
    if 'operatingMargins' in f:
        out.append(f"営業利益率 {f['operatingMargins']*100:.1f}%")
    if 'freeCashflow' in f:
        unit = f.get('_currency', '通貨未確認')
        out.append(f"FCF {f['freeCashflow']/1e8:+,.1f}億{unit}")
    if 'totalDebt' in f and 'totalCash' in f:
        unit = f.get('_currency', '通貨未確認')
        out.append(f"現金 {f['totalCash']/1e8:,.1f}億{unit}／負債 {f['totalDebt']/1e8:,.1f}億{unit}")
    return '、'.join(out) if out else '数値未取得'


def choose(universe, stats, recent, today):
    """No forced repeats: fewer than three is preferable to fabricated new catalysts."""
    selected = {}
    for market in ('JP', 'US'):
        available = [x for x in universe if x['market'] == market and x['ticker'] in stats and x['ticker'] not in recent]
        if today.weekday() == 6:
            candidates = [x for x in available if stats[x['ticker']]['weekly_pct'] is not None]
            movers = sorted(candidates, key=lambda x: abs(stats[x['ticker']]['weekly_pct']), reverse=True)[:3]
            mode = '週間変動率（監視銘柄内）'
        elif today.weekday() == 0:
            # Monday is prospective watchlist, ranked by prior-day volatility; NOT an actual forecast.
            movers = sorted(available, key=lambda x: abs(stats[x['ticker']]['change_pct']), reverse=True)[:3]
            mode = '今週の注目候補（前営業日の変動率を基に選定・予想ではない）'
        else:
            movers = sorted(available, key=lambda x: abs(stats[x['ticker']]['change_pct']), reverse=True)[:3]
            mode = '直近営業日の変動率（監視銘柄内）'
        used = {x['ticker'] for x in movers}
        pool = sorted([x for x in available if x['ticker'] not in used and stats[x['ticker']]['bar_count'] >= 1000], key=lambda x: stats[x['ticker']]['position5'])
        # Yahoo fundamentals are costly and rate-limited. Check a short shortlist.
        scored = []
        for x in pool[:14]:
            f = fundamentals(x['ticker'])
            p = financial_score(f)
            if p is not None:
                scored.append((stats[x['ticker']]['position5'] + p, x, f))
            time.sleep(0.2)
        scored.sort(key=lambda t: t[0])
        lows = [dict(x, financials=f) for _, x, f in scored[:3]]
        selected[market] = {'movers': movers, 'lows': lows, 'mode': mode}
    return selected


def recent_symbols(history, today):
    return {sym for day, symbols in history.items()
            if 0 < (today-date.fromisoformat(day)).days <= 14
            for sym in symbols}


def maybe_ai_summary(payload):
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=50.0)
        response = client.responses.create(
            model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
            instructions=(
                'あなたは金融データの編集者です。入力JSONの数値とニュース見出し以外の事実を追加しない。'
                '200〜350字の日本語で市場全体の観察と今後の注目点を書く。'
                'ニュース見出しは未検証であるため、見出しだけから出来事を断定しない。'
                '事実と予想を明示的に分ける。投資推奨しない。'
            ),
            input=json.dumps(payload, ensure_ascii=False),
            max_output_tokens=450,
        )
        return response.output_text.strip()
    except Exception as exc:
        LOG.warning('OpenAI summary unavailable: %s', exc)
        return None


def render_report(today, selected, stats, indexes, market_news, ai_summary):
    mode = '週間レビュー' if today.weekday() == 6 else ('今週の注目候補' if today.weekday() == 0 else '前営業日の注目変動')
    lines = [f'# 株式日報｜{today.isoformat()}（{ "月火水木金土日"[today.weekday()] }）',
             f'**日本時間の生成日：{today.isoformat()}／{mode}**',
             '', '株価はデータ提供元で確認できた**直近の通常取引終値**です。日本・米国それぞれの最終取引日を明記しています。',
             '監視対象銘柄から選定しており、市場全銘柄の値上がり率ランキングではありません。',
             '', '## 市場指数（直近取得値）', '', '| 指数 | 最終取引日 | 終値 | 前日比 |', '|---|---|---:|---:|']
    for ticker, name, market in [('^N225','日経平均','JP'),('^TOPX','TOPIX','JP'),('^GSPC','S&P 500','US'),('^IXIC','NASDAQ総合','US'),('^DJI','NYダウ','US')]:
        if ticker in indexes:
            m = indexes[ticker]
            lines.append(f"| {name} | {m['date']} | {m['close']:,.2f} | {m['change']:+,.2f}（{m['change_pct']:+.2f}%） |")
    lines += ['', '## 市場関連ニュース（見出し・公開日時を参照）', '']
    if market_news:
        for n in market_news:
            lines.append(f"- [{escape(n['title'])}]({n['url']}) — {escape(n['published'])}")
    else:
        lines.append('ニュースの取得に失敗しました。')
    if ai_summary:
        lines += ['', '### AIによる補足分析（見通しを含む）', '', escape(ai_summary)]
    for market, flag in [('JP','日本株'),('US','米国株')]:
        selection = selected[market]
        lines += ['', f"## {flag}｜{selection['mode']} 3銘柄", '']
        if not selection['movers']:
            lines += ['取得可能な候補がありませんでした。', '']
        for x in selection['movers']:
            lines += stock_section(x, stats[x['ticker']], market, low=False)
        if len(selection['movers']) < 3:
            lines += [f"**注記：条件を満たす候補が{len(selection['movers'])}銘柄のため、重複銘柄で補充していません。**", '']
        lines += ['', f'## {flag}｜過去5年安値圏候補 3銘柄', '',
                  '価格レンジ位置は「(現在値−5年安値)÷(5年高値−5年安値)」。取得できた過去5年の日足（少なくとも約4年分）を使用し、配当再投資は含みません。', '']
        for x in selection['lows']:
            lines += stock_section(x, stats[x['ticker']], market, low=True)
        if len(selection['lows']) < 3:
            lines += [f"**注記：業績・財務データを確認できた候補が{len(selection['lows'])}銘柄のため、未確認銘柄で補充していません。**", '']
    lines += ['', '---', '', '**データの注意：** 株価・5年高安値はYahoo Financeの非公式取得経路を使用します。データ遅延、株式分割調整、欠損、提供元の仕様変更があり得ます。5年高安値は取得できた日足データに限ります。',
              '**ニュースの注意：** GoogleニュースRSSの見出しは参考情報であり、記事本文や一次情報の確認を保証しません。',
              '**投資助言ではありません。** 安値圏は割安や反発を保証しません。']
    return '\n'.join(lines) + '\n'


def stock_section(x, m, market, low):
    ticker = x['ticker']
    name = escape(x['name'])
    lines = [f"### {name}｜{ticker}",
             f"[株価・5年チャート]({quote_link(ticker, market)})", '',
             f"**直近終値：{fmt_price(m['close'],market)}｜前日比：{fmt_delta(m['change'],m['change_pct'],market)}**",
             f"**取引日：{m['date']}（現地市場の通常取引終値）**", '',
             f"**事業概要（登録情報）：** {escape(x['business'])}",
             f"**主要ブランド・サービス（登録情報）：** {escape(x['brands'])}",
             f"**主要リスク（登録情報）：** {escape(x['risks'])}", '']
    if low:
        f = x.get('financials', {})
        lines += [f"**5年高値：{fmt_price(m['high5'],market)}／5年安値：{fmt_price(m['low5'],market)}／現在のレンジ位置：{m['position5']:.1f}%**",
                  '', '```text', range_graph(m), '```',
                  f"**業績・財務（取得値）：** {describe_financials(f,market)}",
                  f"**事業環境：** {escape(x['environment'])}",
                  f"**事実・注目理由：** 5年価格レンジの下側に位置する候補。現在位置は{m['position5']:.1f}%です。",
                  '**予想・確認点：** 業績、財務、事業環境の改善が継続するかを確認。安値が底値とは限りません。', '']
    else:
        lines += [f"**事実・注目理由：** 直近営業日の前日比{m['change_pct']:+.2f}%、週間騰落率" +
                  (f"{m['weekly_pct']:+.2f}%" if m['weekly_pct'] is not None else '未算出') + '。',
                  f"**事業環境：** {escape(x['environment'])}",
                  '**予想・確認点：** 変動の継続は未確定。次回決算・一次情報を確認。', '']
    news = news_search(x['name'], days=7, limit=2)
    if news:
        lines.append('**関連報道の見出し（直接の株価変動要因とは限りません）：**')
        for n in news:
            lines.append(f"- [{escape(n['title'])}]({n['url']})（{escape(n['published'])}）")
        lines.append('')
    return lines


def build_html(markdown_text, title):
    content = markdown.markdown(markdown_text, extensions=['tables','fenced_code'])
    css = '''body{font-family:-apple-system,BlinkMacSystemFont,"Noto Sans JP",sans-serif;background:#f6f8fb;color:#17212f;margin:0;line-height:1.7}main{max-width:880px;margin:30px auto;background:white;padding:36px;border-radius:18px;box-shadow:0 3px 20px #0001}h1,h2,h3{line-height:1.35}h1{font-size:1.8rem}h2{border-bottom:1px solid #dbe2e8;padding-bottom:10px;margin-top:40px}h3{margin-top:28px}a{color:#155bb6}table{width:100%;border-collapse:collapse;display:block;overflow-x:auto}th,td{border:1px solid #dbe2e8;padding:7px 10px;text-align:left;white-space:nowrap}th{background:#f1f4f8}pre{background:#f3f6f9;padding:16px;overflow:auto}p{margin:10px 0}@media(max-width:650px){main{margin:0;padding:16px;border-radius:0}h1{font-size:1.4rem}}'''
    return '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+css+'</style></head><body><main><p><a href="../index.html">← 日報一覧へ</a></p>'+content+'</main></body></html>'


def make_index():
    reports = sorted((ROOT/'reports').glob('????-??-??.md'), reverse=True)
    items = ''.join(f'<li><a href="reports/{p.stem}.html">{p.stem} の株式日報</a></li>' for p in reports)
    return '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>株式日報アーカイブ</title><style>body{font-family:system-ui,sans-serif;max-width:700px;margin:40px auto;padding:16px;line-height:2}a{color:#155bb6}li{border-bottom:1px solid #ddd}</style></head><body><h1>株式日報アーカイブ</h1><p>毎朝7時頃（日本時間）に更新。GitHub Actionsの混雑により遅れる場合があります。</p><ul>'+items+'</ul></body></html>'


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    now = datetime.now(JST)
    today = date.fromisoformat(os.environ['REPORT_DATE']) if os.getenv('REPORT_DATE') else now.date()
    universe = load_json(ROOT/'config/universe.json', [])
    if not universe:
        raise RuntimeError('config/universe.json is empty')
    history_path = ROOT/'data/history.json'
    history = load_json(history_path, {})
    tickers = [x['ticker'] for x in universe]
    index_symbols = ['^N225','^TOPX','^GSPC','^IXIC','^DJI']
    bars = get_history(tickers+index_symbols)
    stats = {sym: m for sym, frame in bars.items() if (m := metrics(frame,today))}
    if sum(s in stats for s in tickers) < 12:
        raise RuntimeError('Insufficient live price data; report NOT published')
    selected = choose(universe, stats, recent_symbols(history,today), today)
    market_news = news_search('日経平均 米国株 金利 決算', days=3, limit=5)
    brief = {'date': today.isoformat(), 'indexes': {s:stats[s] for s in index_symbols if s in stats},
             'market_headlines': market_news,
             'selected': {market:{k:[{'ticker':x['ticker'],'name':x['name'],'metrics':stats[x['ticker']]} for x in selected[market][k]] for k in ('movers','lows')} for market in ('JP','US')}}
    ai_summary = maybe_ai_summary(brief)
    report = render_report(today, selected, stats, {s:stats[s] for s in index_symbols if s in stats}, market_news, ai_summary)
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'docs/reports').mkdir(parents=True,exist_ok=True)
    (ROOT/'reports'/f'{today.isoformat()}.md').write_text(report,encoding='utf-8')
    (ROOT/'docs/reports'/f'{today.isoformat()}.html').write_text(build_html(report, f'株式日報 {today.isoformat()}'),encoding='utf-8')
    (ROOT/'docs/index.html').write_text(make_index(),encoding='utf-8')
    history[today.isoformat()] = [x['ticker'] for market in ('JP','US') for kind in ('movers','lows') for x in selected[market][kind]]
    history_path.write_text(json.dumps(dict(sorted(history.items())), ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Generated {today.isoformat()}: {len(history[today.isoformat()])} stocks; URL under /reports/{today.isoformat()}.html')

if __name__ == '__main__':
    main()