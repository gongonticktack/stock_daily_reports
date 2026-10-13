🌐 **Webアプリ：[STOCK NEWSを開く](https://gongonticktack.github.io/stock_daily_reports/)**

# STOCK NEWS — 日本株・米国株の日刊レポート

## 概要

日本株・米国株の株価、値動き、安値圏候補、市場ニュースをまとめて、日付別の株式日報を公開するサイトです。Pythonでレポートを生成し、GitHub ActionsとGitHub Pagesで配信します。日別サマリー、詳細分析、日英表示切替に対応しています。

[公開サイトを開く](https://gongonticktack.github.io/stock_daily_reports/)

## 主な機能

- 日本株・米国株の注目銘柄と株価・前日比・チャートリンクの掲載。
- 曜日に応じた値動き候補と、過去の価格レンジに基づく安値圏候補の選定。
- 選定履歴による銘柄重複の抑制。
- 日付別サマリーと銘柄ごとの詳細への移動。
- 日英切替、過去記事の閲覧・再構成。

## 推奨要件

| 用途 | 環境 |
| --- | --- |
| 閲覧 | 現行ブラウザ |
| ローカル生成 | Python 3.11、インターネット接続 |
| 定期公開 | GitHub Actions、GitHub Pages |
| AI要約 | OpenAI APIキー（任意） |

## 必要なライブラリ

`requirements.txt`から導入します。

| ライブラリ | 用途 |
| --- | --- |
| yfinance、pandas | 株価取得・集計 |
| requests、feedparser、beautifulsoup4 | ニュース取得・解析 |
| Markdown | レポートのHTML化 |
| deep-translator | 翻訳 |
| openai | 任意のAI要約 |

## 使い方

### 閲覧

公開サイトで日付を選び、サマリーから対象銘柄の詳細を開きます。日英ボタンで表示言語を切り替えられます。

### 自動公開

1. GitHub Actionsを有効にします。
2. Settings → Pagesで公開元をGitHub Actionsに設定します。
3. `config/universe.json`の銘柄情報を確認・調整します。
4. AI要約を利用する場合だけSecretsに`OPENAI_API_KEY`を登録します。
5. Actionsの「Japanese stock daily report」→「Run workflow」で生成します。

予約実行は06:17 JST、予備実行は06:47 JSTです。07:00頃の公開を目指しますが、開始時刻は遅れる場合があります。当日レポートがあれば予備実行の再生成を省略します。手動実行では当日レポートを生成します。

### ローカル生成

ルートで実行します。

```bash
python -m venv .venv
# OSに応じて .venv を有効化
python -m pip install -r requirements.txt
python scripts/daily_report.py
python scripts/build_site.py
python -m http.server 8000 --directory docs
```

`http://localhost:8000/`を開きます。既存レポートの表示だけ再構築する場合は `python scripts/build_site.py` を実行します。

## 設定

| 設定 | 内容 |
| --- | --- |
| `config/universe.json` | 銘柄候補と登録情報 |
| `config/backfill.json` | 過去分再構成の対象 |
| `OPENAI_API_KEY` | 任意のAI要約キー |
| `OPENAI_MODEL` | 要約モデル。コード既定値は`gpt-4.1-mini` |
| `REPORT_DATE` | 対象日。未指定時は日本時間の当日 |

過去分再構成は `python scripts/backfill.py` で実行します。過去配信の完全な復元ではなく、利用可能なデータからの作成です。

## フォルダ構成

| 相対パス | 役割 |
| --- | --- |
| `scripts/daily_report.py` | 株価・ニュース取得、銘柄選定、日報生成 |
| `scripts/build_site.py` | 日英サマリー・詳細サイトの生成 |
| `scripts/backfill.py` | 過去分再構成 |
| `scripts/create_universe.py` | 銘柄候補設定の生成補助 |
| `config/` | 銘柄候補・再構成設定 |
| `reports/` | 日付別Markdownレポート |
| `docs/` | 公開サイト、サマリー・詳細HTML・共通CSS |
| `data/` | 選定履歴、翻訳キャッシュ |
| `tests/` | 日報とサイト生成のテスト |
| `.github/workflows/daily.yml` | 定期生成・保存・Pages公開 |
| `requirements.txt` | Python依存関係 |

## 仕組み

株価とニュースを取得し、曜日の条件と履歴を使って対象銘柄を選びます。Markdownの日報からサマリー・詳細HTMLを生成し、Actionsが結果と選定履歴をコミットしてPagesへ公開します。十分な株価データが取得できなければ日報生成を停止します。

## 確認方法

```bash
python -m unittest discover -s tests -v
```

## トラブル対処

- 日報更新失敗：Actionsの失敗ステップ、当日のレポート、価格取得先の応答を確認します。
- サマリーと詳細が不一致：`scripts/build_site.py`を実行して再構築します。
- 翻訳が更新されない：`data/`の翻訳キャッシュと外部翻訳先の応答を確認します。
- Pages未公開：公開元をGitHub Actionsに設定し、Pagesデプロイ結果を確認します。

株価の基準日時・通貨・休場日は市場ごとに異なります。表示値や銘柄の評価は元データと照合してください。
