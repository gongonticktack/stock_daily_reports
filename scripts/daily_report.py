#!/usr/bin/env python3
"""Japanese daily stock report: data-first, no invented quotes or 5y ranges."""
from __future__ import annotations
import html
import json
import logging
import os
import re
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


CSS = '''
:root{color-scheme:dark;--bg:#090917;--panel:#151329;--panel2:#201b39;--line:rgba(183,162,255,.19);--text:#f5f2ff;--muted:#b2aecb;--accent:#bba2ff;--blue:#8098ff;--pink:#e5b3ff;--glow:rgba(135,96,255,.22)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--text);font:15px/1.85 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;background:radial-gradient(ellipse 75% 40% at 7% -10%,rgba(117,77,236,.32),transparent 80%),radial-gradient(ellipse 55% 35% at 100% 12%,rgba(71,96,237,.22),transparent 80%),#090917;min-height:100vh;letter-spacing:.012em}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.22;background-image:linear-gradient(rgba(171,150,255,.09) 1px,transparent 1px),linear-gradient(90deg,rgba(171,150,255,.09) 1px,transparent 1px);background-size:52px 52px;mask-image:linear-gradient(to bottom,#000,transparent 82%);z-index:-1}
a{color:#c8b7ff;text-decoration:none;transition:color .2s}a:hover{color:#e9ddff}a:focus-visible{outline:2px solid #d7c6ff;outline-offset:4px;border-radius:5px}
header{position:sticky;top:0;z-index:20;background:rgba(12,11,29,.78);border-bottom:1px solid var(--line);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px)}
.top{max-width:1120px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:15px 24px}
.brand{color:#fff;font-size:1.12rem;letter-spacing:.07em;font-weight:850}.brand b{color:var(--accent)}nav{display:flex;gap:10px;align-items:center}nav a{font-size:.84rem;color:#d5cfee;padding:7px 12px;border:1px solid rgba(178,154,255,.17);border-radius:12px;background:rgba(255,255,255,.035)}
.wrap,main{max-width:1120px;margin:0 auto;padding:30px 24px 90px}
.hero{position:relative;overflow:hidden;margin:12px 0 28px;padding:clamp(28px,5vw,58px);border:1px solid rgba(184,157,255,.28);border-radius:28px;background:linear-gradient(115deg,rgba(108,73,208,.25),rgba(51,56,122,.19) 60%,rgba(150,104,234,.13));box-shadow:inset 0 1px rgba(255,255,255,.12),0 28px 85px rgba(0,0,0,.25);backdrop-filter:blur(22px)}
.hero:after{content:"";position:absolute;width:330px;height:330px;border-radius:50%;background:radial-gradient(circle,rgba(180,125,255,.28),transparent 68%);right:-100px;top:-140px;pointer-events:none}
.eyebrow,.kicker{font-size:.73rem;font-weight:800;letter-spacing:.2em;color:#c9b7ff;text-transform:uppercase}
.hero h1{font-size:clamp(2.5rem,7vw,5.2rem);letter-spacing:-.055em;line-height:1.12;margin:12px 0 14px;font-weight:850;background:linear-gradient(110deg,#fff 15%,#d9c2ff 65%,#9baaff);color:transparent;background-clip:text;-webkit-background-clip:text}
.hero p{max-width:660px;color:#c9c5df;margin:10px 0 0;font-size:1.01rem}
.story,.stock-card,.glass,.archive,.report-table{border:1px solid var(--line);background:linear-gradient(135deg,rgba(41,34,70,.83),rgba(20,20,42,.87));border-radius:23px;box-shadow:inset 1px 1px rgba(255,255,255,.07),0 14px 35px rgba(0,0,0,.2);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
.story,.stock-card,.glass{padding:clamp(20px,3vw,30px);transition:transform .2s,border-color .2s,box-shadow .2s}
.story:hover,.stock-card:hover,.glass:hover{transform:translateY(-3px);border-color:rgba(193,169,255,.48);box-shadow:0 22px 48px rgba(23,15,58,.42)}
.news{display:grid;gap:18px}.story:first-child{background:linear-gradient(125deg,rgba(83,60,146,.68),rgba(25,24,54,.92));border-color:rgba(195,166,255,.44)}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px;color:var(--muted);font-size:.78rem}
.tag{border:1px solid rgba(192,168,255,.38);border-radius:100px;background:rgba(155,117,255,.15);padding:3px 11px;color:#dfceff;font-weight:750}
.story h2{font-size:clamp(1.14rem,2.6vw,1.55rem);line-height:1.48;letter-spacing:-.02em;margin:17px 0 12px;color:#fff}
.story p{color:#d1cde2;margin:11px 0}.why{border-left:3px solid #a58cff;padding-left:15px;color:#e2d9ff!important;background:linear-gradient(90deg,rgba(158,118,255,.09),transparent);padding-top:7px;padding-bottom:7px}
.link,.cta{display:inline-flex;align-items:center;gap:8px;margin-top:10px;border-radius:13px;padding:10px 17px;background:linear-gradient(115deg,#a88bff,#849cff);color:#100d25;font-weight:800;box-shadow:0 8px 25px rgba(110,91,231,.24)}.link:hover,.cta:hover{color:#0b0820;filter:brightness(1.12)}
.archive{margin-top:36px;padding:24px}.archive h2{margin:0 0 15px;font-size:1.06rem;letter-spacing:.07em}.archive ul{margin:0;padding:0;list-style:none;display:grid;gap:10px}.archive li a{display:block;padding:12px 15px;border-radius:13px;background:rgba(160,138,255,.07);border:1px solid rgba(190,166,255,.1)}.archive li a:hover{background:rgba(165,139,255,.16)}
footer{margin-top:50px;border-top:1px solid var(--line);padding-top:20px;font-size:.78rem;color:var(--muted)}
@media(max-width:620px){.top{padding:12px 15px}.wrap,main{padding:20px 14px 70px}.hero{border-radius:21px;padding:26px 22px}.story,.stock-card,.glass{border-radius:19px}nav{gap:5px}nav a{padding:6px 9px;font-size:.75rem}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}

.report{max-width:1040px}.report>h1{font-size:clamp(1.75rem,4vw,3rem);line-height:1.3;letter-spacing:-.04em;margin:18px 0 8px}.report>h2{margin:42px 0 18px;padding-bottom:11px;border-bottom:1px solid rgba(190,164,255,.26);font-size:clamp(1.3rem,3vw,1.75rem);letter-spacing:-.02em}.report>h3{font-size:1.16rem}
.report p,.report li{color:#d4d0e6}.report p{margin:13px 0}.report strong{color:#f5f0ff}.report>p:first-of-type{color:#cbbaff}
.report table{width:100%;border-collapse:separate;border-spacing:0;border:1px solid var(--line);border-radius:17px;overflow:hidden;display:block;overflow-x:auto;background:rgba(30,25,54,.72)}.report th,.report td{padding:11px 14px;border-bottom:1px solid rgba(180,160,255,.13);text-align:left;white-space:nowrap}.report th{color:#d9c7ff;background:rgba(137,107,221,.19);font-size:.82rem}.report tr:last-child td{border-bottom:0}.report pre{overflow-x:auto;padding:15px;border-radius:14px;background:#101126;border:1px solid var(--line);color:#d5cbff}
.report .stock-card{margin:20px 0;padding:23px 25px}.stock-card h3{margin:0 0 10px;font-size:1.28rem;color:#f2eaff}.stock-card>p:nth-of-type(2){background:rgba(131,109,238,.11);padding:12px 15px;border-radius:12px;border:1px solid rgba(166,144,255,.15)}.stock-card ul{padding-left:20px}.stock-card a{overflow-wrap:anywhere}
.archive-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:15px}.archive-grid .glass{display:block;color:#f3efff}.archive-grid .glass span{display:block;font-size:.75rem;color:#b9addb;letter-spacing:.13em;margin-bottom:8px}.archive-grid .glass strong{font-size:1.15rem}.archive-grid .glass small{display:block;color:#c4bfd9;margin-top:8px}
.report hr{border:0;border-top:1px solid var(--line);margin-top:35px}.report>ul{padding-left:23px}
'''

def build_html(markdown_text, title):
    content = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="theme-color" content="#0a0919">'
        '<meta name="description" content="日本株と米国株の毎日のマーケットレポート">'
        '<title>' + html.escape(title) + '</title>'
        '<link rel="stylesheet" href="../theme.css"></head><body>'
        '<header class="topbar"><div class="topbar-inner">'
        '<a class="brand" href="../index.html">MARKET <span>BRIEF.</span></a>'
        '<nav><a href="../index.html">最新・アーカイブ</a></nav>'
        '</div></header>'
        '<main class="site-wrap"><article class="report-content">'
        '<div class="kicker">DAILY MARKET INTELLIGENCE · JAPAN / US</div>'
        + content +
        '</article><footer class="site-footer">'
        '株価・ニュースの取得日時とデータの注意事項をご確認ください。投資助言ではありません。'
        '</footer></main></body></html>'
    )


def make_index():
    reports = sorted((ROOT / 'reports').glob('????-??-??.md'), reverse=True)
    latest = reports[0].stem if reports else None
    hero = (
        '<section class="hero"><div class="eyebrow">DAILY MARKET INTELLIGENCE</div>'
        '<h1>Market <span class="gradient-text">Brief.</span></h1>'
        '<p>日本株・米国株の値動き、5年安値圏、注目ニュースをひとつに。'
        '毎朝7時頃（日本時間）に更新するマーケットダイジェスト。</p></section>'
    )
    feature = (
        '<section class="feature-grid">'
        '<a class="feature-card" href="reports/' + latest + '.html">'
        '<div class="feature-icon">↗</div><div class="eyebrow">LATEST REPORT</div>'
        '<h2>最新の株式日報</h2><p>' + latest + ' の市場レポートを読む</p>'
        '<span class="card-arrow">レポートを開く ↗</span></a>'
        '<a class="feature-card" href="#archive">'
        '<div class="feature-icon">◷</div><div class="eyebrow">HISTORY</div>'
        '<h2>過去のレポート</h2><p>日付別に保存された過去の相場を振り返る</p>'
        '<span class="card-arrow">アーカイブを見る ↓</span></a></section>'
    ) if latest else '<section class="glass" style="padding:28px">初回レポートを生成しています。</section>'
    archive = ''.join(
        '<li><a href="reports/' + p.stem + '.html"><span>' + p.stem +
        ' の株式日報</span><span>JP / US</span></a></li>' for p in reports
    )
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="theme-color" content="#0a0919">'
        '<title>Market Brief｜日本株・米国株の日報</title>'
        '<link rel="stylesheet" href="theme.css"></head><body>'
        '<header class="topbar"><div class="topbar-inner">'
        '<a class="brand" href="index.html">MARKET <span>BRIEF.</span></a>'
        '<nav><a href="#archive">ARCHIVE</a></nav></div></header>'
        '<main class="site-wrap">' + hero + feature +
        '<section class="archive" id="archive"><h2>ARCHIVE / 過去の株式日報</h2>'
        '<ul>' + archive + '</ul></section>'
        '<footer class="site-footer">データの遅延・欠損があり得ます。投資助言ではありません。'
        'GitHub Actionsの起動時刻は前後する場合があります。</footer>'
        '</main></body></html>'
    )


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