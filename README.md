# 日本株・米国株の日刊レポート（GitHub Actions + GitHub Pages）

🌐 **公開サイト（GitHub Pages）：[株式NEWSを開く](https://gongonticktack.github.io/stock_daily_reports/)**

毎朝 **日本時間7:00頃**、日本株と米国株の日報を生成し、`reports/YYYY-MM-DD.md` と `docs/reports/YYYY-MM-DD.html` に保存します。GitHub Pagesで日付別に閲覧でき、ChatGPTの会話は肥大化しません。

## 動作と制約

- 月曜日：今週の注目候補、日本3＋米3。直近の値動きから選ぶ**監視候補**であり、上昇予測ではありません。
- 火〜土曜日：前営業日に値動きが大きかった銘柄、日本3＋米3。
- 日曜日：週間変動率の大きい銘柄、日本3＋米3。
- 毎日：5年レンジ下側の日本3＋米3。業績と財務の取得値で足切り・順位補正。
- 過去14日間の採用銘柄は原則除外。候補不足なら不足と表示し、材料のない再掲載をしません。
- 各銘柄：銘柄名、チャートリンク（名前の直下）、最終取引日、終値、前日比（金額・率）、事業概要、ブランド、注目理由、リスク、事実・予想の区別。
- 5年チャートはYahoo Financeへのリンク。レポート内の縦図は**価格レンジ位置図**であり、時系列の値動きではありません。
- 取引休場日には直近営業日終値を表示。**GitHub Actionsの起動は遅延し得る**ため、07:00ぴったりは保証できません。
- `config/universe.json` の監視対象186銘柄（日本83・米国103）から選定。**市場全銘柄の値上がり率ランキングではありません。**
- 株価：`yfinance`（非公式Yahoo Finance取得経路）。5年高安値：取得できた日足OHLC。分割調整を含み、配当再投資は含まない。取得失敗なら数値を捏造しない。
- ニュース：GoogleニュースRSSの見出しとリンクのみ。記事本文・一次情報の検証までは自動化していない。**見出しを材料の確定原因と断定しません。**
- 業績・財務：Yahoo Finance `Ticker.info` で取得できた指標のみ。欠損なら安値候補を減らす場合があります。
- OpenAI APIキーは任意。設定すると取得済みデータに基づく市場コメントを追加。**ChatGPT Plus料金とは別のAPI従量課金**です。
- Google News RSS・yfinanceは非公式/無償経路であり、提供元の変更、アクセス制限、利用条件の確認が必要です。商用・高信頼運用には正規の有料マーケットデータAPIを推奨します。

## 導入（約15分）

1. GitHubで新しいリポジトリ（例 `stock-daily-report`）を作成。GitHub Pagesで公開するため、公開範囲を検討してください。
2. このテンプレートの全ファイルをリポジトリのルートにアップロード。**`.github/workflows/daily.yml` の隠しフォルダも含めて**アップロードします。
3. GitHubの **Settings → Pages → Build and deployment → Source: GitHub Actions** を選択します。
4. **Settings → Actions → General → Workflow permissions** で、必要に応じて `Read and write permissions` を有効にします（組織ポリシーによって設定不可の場合があります）。
5. （任意）**Settings → Secrets and variables → Actions → New repository secret** で `OPENAI_API_KEY` を追加。未設定でも株価・ニュースから日報を生成します。**キーをファイルやコミットに書かないこと。**
6. **Actions → Japanese stock daily report → Run workflow** を押して初回手動実行。
7. 実行が成功したら、**Settings → Pages** に表示されるURLを開きます。通常 `https://<ユーザー名>.github.io/<リポジトリ名>/` です。URLは実際のPages設定で確認してください。
8. 以後、GitHub Actionsが毎日 **22:00 UTC = 翌07:00 JST** に起動します。リポジトリの既定ブランチに保存されます。

### スマートフォンで閲覧

PagesのURLをiPhoneのSafariで開き、共有 → ホーム画面に追加。日報一覧がアプリ風に開けます。必要ならGitHub Actionsの失敗通知はGitHubの通知設定から受け取れます。

## ファイル構成

```text
.github/workflows/daily.yml  # スケジュール・生成・GitHub Pages公開
config/universe.json          # 銘柄情報・ブランド・リスク・事業環境
scripts/daily_report.py       # 株価・ニュース・選定・日報生成
scripts/create_universe.py    # 監視銘柄リストを再生成（任意）
data/history.json             # 14日間の重複回避履歴
reports/YYYY-MM-DD.md         # 日付別Markdown原本
docs/index.html               # 日報一覧
docs/summary/YYYY-MM-DD.html  # 日付別の銘柄サマリ（トップは最新日）
docs/reports/YYYY-MM-DD.html  # 公開用日報
requirements.txt              # Python依存パッケージ
tests/test_report.py          # オフライン単体テスト
tests/test_site.py            # 日英表示・銘柄アンカー・日付別サマリのテスト
```

トップの「詳しい分析を見る」は当日の詳細レポートの銘柄見出しへ移動します。IDは市場・分類・ティッカーと同一分類内の出現回数から決定し、同名銘柄やJP/USの重複を区別します。日英の見出しIDも分離し、保存された表示言語に応じてスクロールします。固定ヘッダー分の余白を設けています。

日付別サマリは保存済みの `reports/YYYY-MM-DD.md` から生成し、アーカイブにはサマリへのリンクを表示します。ページ先頭の前日／翌日ボタンで前後の公開済み日へ移動でき、最古・最新では該当ボタンを無効化します。サマリは隣の日のサマリ、詳細は隣の日の詳細へ移動します。毎朝の既存Actionsでサマリも保存・公開します。日英切替、翻訳失敗時の原文と注意表示、株価・日付の保持は継続します。

## ローカル実行

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/daily_report.py
```

日付を指定する場合は `REPORT_DATE=2026-10-11 python scripts/daily_report.py`。Windows PowerShellでは `$env:REPORT_DATE="2026-10-11"; python scripts/daily_report.py`。過去日付の完全な履歴再現には、当時のニュースと当時の財務情報が必要なため、このスクリプトでは保証できません。

## 運用上の注意

- 監視銘柄は日本83・米国103で、14日間毎日6銘柄ずつ重複を完全排除するには日本株側が最大1銘柄不足する可能性があります。市場休場や財務データ欠損でも候補が減ります。
- `data/history.json` はリポジトリにコミットされます。`reports/` を削除しても、履歴を残す限り重複回避が継続します。
- 日曜日は「その週の最終終値と前週末終値」を比較します。月曜日は前営業日の変動率から**注目候補**を選ぶため、材料のある銘柄を厳密に予測するものではありません。
- 本コードは運用の出発点です。**実際のライブデータ取得・GitHub Pages公開まで、この配布環境での統合動作は未検証**です。初回手動実行で取得状況とレポートの内容を必ず確認してください。
- APIキーの漏洩防止、マーケットデータの再配布条件、GitHub Pagesの公開範囲を確認してください。
- **投資助言ではありません。**
