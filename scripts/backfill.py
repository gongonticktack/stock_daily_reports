#!/usr/bin/env python3
"""Reconstruct missing dated editions; never substitute current quotes or fundamentals."""
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
import feedparser
import pandas as pd
import requests
import daily_report as report

ROOT = Path(__file__).resolve().parents[1]

def historical_news(day, days=3):
    cutoff = datetime.combine(day, datetime.min.time(), report.JST).replace(hour=7)
    url = 'https://news.google.com/rss/search?' + urlencode({
        'q': f'日経平均 米国株 金利 決算 after:{(day-timedelta(days=days)).isoformat()} before:{(day+timedelta(days=1)).isoformat()}',
        'hl': 'ja', 'gl': 'JP', 'ceid': 'JP:ja'})
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        result = []
        for item in feedparser.parse(response.content).entries:
            stamp = item.get('published_parsed')
            if not stamp:
                continue
            import calendar
            from datetime import timezone
            published = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc)
            if not cutoff-timedelta(days=days) <= published <= cutoff:
                continue
            result.append({'title': item.get('title', ''), 'url': item.get('link', ''),
                           'published': published.astimezone(report.JST).isoformat()})
        return sorted(result, key=lambda x:x['published'], reverse=True)[:5]
    except Exception as exc:
        logging.warning('Historical news unavailable for %s: %s', day, exc)
        return []

def missing_days(config):
    current = date.fromisoformat(config['start'])
    end = min(date.fromisoformat(config['end']), datetime.now(report.JST).date()-timedelta(days=1))
    result = []
    while current <= end:
        path = ROOT/'reports'/f'{current}.md'
        if not path.exists() or '外部公開前プレビュー' in path.read_text(encoding='utf-8'):
            result.append(current)
        current += timedelta(days=1)
    return result

def price_window(frame, day):
    start = (pd.Timestamp(day)-pd.DateOffset(years=5)).date()
    return frame.loc[[start <= report.session_date(index) < day for index in frame.index]]


def run():
    logging.basicConfig(level=logging.INFO)
    config_path = ROOT/'config/backfill.json'
    if not config_path.exists():
        return
    days = missing_days(json.loads(config_path.read_text()))
    if not days:
        print('Historical editions already present')
        return
    universe = report.load_json(ROOT/'config/universe.json', [])
    symbols = [x['ticker'] for x in universe]
    indexes = ['^N225','^TOPX','^GSPC','^IXIC','^DJI']
    start = (pd.Timestamp(days[0])-pd.DateOffset(years=5)).date().isoformat()
    bars = report.get_history(symbols+indexes, start=start, end=days[-1].isoformat())
    history_path = ROOT/'data/history.json'
    history = report.load_json(history_path, {})
    original_news = report.news_search
    report.news_search = lambda *args, **kwargs: []  # No current company headlines in past editions.
    try:
        for day in days:
            stats = {}
            for symbol, frame in bars.items():
                past = price_window(frame, day)
                metric = report.metrics(past, day)
                if metric:
                    stats[symbol] = metric
            if sum(symbol in stats for symbol in symbols) < 12:
                raise RuntimeError(f'Insufficient dated price data for {day}; refusing to fabricate')
            selected = report.choose(universe, stats, report.recent_symbols(history, day), day, historical=True)
            text = report.render_report(day, selected, stats, {s:stats[s] for s in indexes if s in stats},
                                        historical_news(day), None)
            text = text.replace('日本時間の生成日：', '日本時間の対象日：').replace('業績・財務データを確認できた候補', '株価履歴の条件を満たす候補')
            notice = ('> **過去分の再構成レポート**：' + datetime.now(report.JST).isoformat(timespec='seconds') +
                      ' に作成。対象日の07:00 JSTより前の取引日までの株価を使用しています。'
                      '当時の配信内容を復元したものではありません。銘柄の登録情報は現在の情報です。'
                      '当時の業績・財務は取得できないため評価保留とし、安値圏候補は価格レンジのみで選定しています。'
                      '個別銘柄の過去ニュースは掲載していません。市場ニュースは公開日時を確認できた見出しのみです。\n\n')
            first, rest = text.split('\n', 1)
            text = first+'\n\n'+notice+rest
            (ROOT/'reports').mkdir(exist_ok=True)
            (ROOT/'reports'/f'{day}.md').write_text(text, encoding='utf-8')
            history[str(day)] = [x['ticker'] for market in ('JP','US') for kind in ('movers','lows')
                                 for x in selected[market][kind]]
            history_path.write_text(json.dumps(dict(sorted(history.items())),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'Reconstructed {day}: {len(history[str(day)])} stocks', flush=True)
    finally:
        report.news_search = original_news

if __name__ == '__main__':
    run()
