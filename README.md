# stock_daily_reports

日本株・米国株の日刊レポートを、GitHub Actionsで毎朝7時（日本時間）頃に生成し、GitHub Pagesで日付別に公開するプロジェクトです。

- 月曜：週間注目候補（日本3・米国3）
- 火〜土曜：直近営業日の変動銘柄（日本3・米国3）
- 日曜：週間変動銘柄（日本3・米国3）
- 毎日：5年安値圏候補（日本3・米国3）
- 過去14日間の重複回避、終値・前日比・5年高安値・関連ニュースを掲載
- 株価・ニュースが取得できない場合は推測値を作らず、取得不能を明記します。

## 公開設定
GitHub → Settings → Pages → Build and deployment → **Source: GitHub Actions** を選択してください。

GitHub → Actions → **Japanese stock daily report** → **Run workflow** で初回実行します。

毎朝7時JSTにスケジュール起動しますが、GitHub Actionsの混雑によって遅れる場合があります。

データはYahoo Financeの非公式経路を使用します。運用前にデータ利用条件を確認してください。ChatGPT Plusとは別のOpenAI API利用料が発生する可能性があります（API利用は任意）。

**このレポートは投資助言ではありません。**
