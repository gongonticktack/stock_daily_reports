"""Developer convenience: rebuild the example watch universe from curated records."""
import json
from pathlib import Path
# ticker | name | business | brands/services | risk | business environment
JP = '''
7203.T|トヨタ自動車|自動車メーカー|トヨタ、レクサス、プリウス|為替、関税、EV競争|世界の自動車需要とハイブリッド車販売
7267.T|本田技研工業|自動車・二輪車メーカー|Honda、Acura、シビック|EV投資、為替、関税|二輪車収益と四輪車再編
7201.T|日産自動車|自動車メーカー|NISSAN、INFINITI、リーフ|財務、販売低迷、構造改革|新車販売と固定費削減
7261.T|マツダ|自動車メーカー|MAZDA、CX-5、ロードスター|為替、関税、米国需要|北米販売と電動化投資
8306.T|三菱UFJフィナンシャル・グループ|銀行・金融グループ|三菱UFJ銀行、三菱UFJ信託銀行|信用費用、金利、規制|金利と貸出需要
8316.T|三井住友フィナンシャルグループ|銀行・金融グループ|三井住友銀行、SMBC日興証券|信用費用、金利|貸出金利と金融収益
8411.T|みずほフィナンシャルグループ|銀行・金融グループ|みずほ銀行、みずほ証券|信用費用、システム|国内金利と企業融資
8308.T|りそなホールディングス|銀行グループ|りそな銀行、埼玉りそな銀行|金利、信用費用|国内金利と個人向け金融
9984.T|ソフトバンクグループ|投資持株会社|Arm、Vision Fund|投資評価、負債、為替|AI投資市場と資金調達
9432.T|NTT|通信・IT企業|ドコモ、OCN、IOWN|設備投資、競争|通信料金とデータセンター需要
9433.T|KDDI|通信事業者|au、UQ mobile、povo|競争、設備投資|携帯通信と金融サービス
9434.T|ソフトバンク|通信事業者|SoftBank、Y!mobile、PayPay|通信競争、負債|通信契約と決済サービス
6758.T|ソニーグループ|エンタメ・電子機器|PlayStation、ソニーミュージック|為替、ゲーム競争|ゲームと映像・音楽IP
7974.T|任天堂|ゲーム機・ゲームソフト|Nintendo Switch、マリオ、ゼルダ|ハード世代交代、為替|新型ゲーム機とソフト販売
9983.T|ファーストリテイリング|衣料品小売|UNIQLO、GU、Theory|為替、中国需要|海外ユニクロの成長
3382.T|セブン＆アイ・ホールディングス|小売・コンビニ|セブン‐イレブン、イトーヨーカドー|競争、再編|コンビニ収益と事業再編
8267.T|イオン|総合小売|イオン、マックスバリュ、まいばすけっと|人件費、消費低迷|食品小売とPB商品の需要
9843.T|ニトリホールディングス|家具・生活用品小売|ニトリ、デコホーム、N+|為替、物流費|家具需要と輸入コスト
6098.T|リクルートホールディングス|人材・HRテクノロジー|Indeed、Glassdoor、SUUMO|雇用市場、競争|米国採用需要と広告市場
4661.T|オリエンタルランド|テーマパーク運営|東京ディズニーランド、東京ディズニーシー|人件費、設備投資|来園者数と客単価
8035.T|東京エレクトロン|半導体製造装置|成膜装置、エッチング装置|半導体市況、輸出規制|半導体設備投資
6857.T|アドバンテスト|半導体検査装置|半導体テスタ、SoCテスト|半導体市況、顧客集中|AI向け半導体テスト需要
6146.T|ディスコ|半導体精密加工装置|ダイシングソー、グラインダ|設備投資、競争|半導体後工程需要
6723.T|ルネサスエレクトロニクス|半導体メーカー|車載MCU、アナログ半導体|在庫調整、車載需要|車載・産業半導体需要
4062.T|イビデン|半導体パッケージ基板|ICパッケージ基板|顧客集中、設備投資|AI半導体向け基板需要
6526.T|ソシオネクスト|半導体設計|カスタムSoC|顧客集中、設計案件|データセンター向けSoC
6323.T|ローツェ|半導体搬送装置|ウエハ搬送ロボット、ロードポート|設備投資、顧客集中|半導体工場の設備投資
6501.T|日立製作所|IT・社会インフラ|Lumada、鉄道システム|大型案件、為替|DXと電力インフラ投資
6702.T|富士通|ITサービス|Uvance、サーバー、システム開発|受託採算、人材確保|企業DXとクラウド移行
6701.T|NEC|IT・通信インフラ|BluStellar、生体認証|官公庁案件、競争|ITサービスと通信インフラ
6503.T|三菱電機|産業機器・電機|FA機器、空調、パワー半導体|品質管理、設備投資|工場自動化と電力需要
6506.T|安川電機|産業ロボット・モーター|MOTOMAN、インバータ|中国景気、設備投資|工場自動化とロボット需要
6954.T|ファナック|FA・産業ロボット|CNC、ロボット、ROBOMACHINE|中国景気、設備投資|工場自動化と工作機械需要
6861.T|キーエンス|FAセンサー・計測|画像センサー、測定器、PLC|設備投資、競争|製造業の自動化投資
6367.T|ダイキン工業|空調機器|ダイキン、うるさらX|為替、原材料|世界の空調需要
7751.T|キヤノン|精密機器|EOS、複合機、医療機器|印刷需要、為替|カメラと商業印刷需要
6753.T|シャープ|家電・電子機器|AQUOS、プラズマクラスター|財務、競争|家電需要と構造改革
6971.T|京セラ|電子部品・機器|セラミック部品、通信機器|設備投資、収益性|半導体部品と産業機器需要
6762.T|TDK|電子部品|積層セラミック部品、電池|スマホ需要、競争|スマホ・車載電子部品
6981.T|村田製作所|電子部品|MLCC、通信モジュール|スマホ需要、競争|AIサーバー・車載部品需要
5802.T|住友電気工業|電線・光通信部品|光ファイバー、ワイヤーハーネス|銅価格、設備投資|データセンターと電力網投資
5801.T|古河電気工業|電線・光通信部品|光ファイバー、電力ケーブル|銅価格、設備投資|通信・電力インフラ投資
5805.T|SWCC|電線・電力インフラ|電力ケーブル、接続部材|銅価格、設備投資|電力網更新需要
6301.T|小松製作所|建設・鉱山機械|KOMATSU、建設機械|中国景気、資源市況|鉱山投資とインフラ投資
6305.T|日立建機|建設機械|油圧ショベル、鉱山機械|建設市況、為替|建設・鉱山設備投資
7011.T|三菱重工業|重工業・防衛|発電設備、防衛機器、航空機|大型案件、原価上昇|防衛予算と発電需要
7012.T|川崎重工業|重工業・輸送機器|航空機、鉄道車両、二輪車|大型案件、為替|防衛・航空宇宙需要
7013.T|IHI|重工業・航空エンジン|航空エンジン、防衛機器|品質問題、設備投資|航空需要と防衛予算
9101.T|日本郵船|海運|コンテナ船、物流、LNG船|運賃市況、燃料費|世界貿易と海運運賃
9104.T|商船三井|海運|LNG船、コンテナ船、物流|運賃市況、燃料費|海運運賃とエネルギー輸送
9107.T|川崎汽船|海運|コンテナ船、自動車船|運賃市況、燃料費|世界貿易と輸送需要
5020.T|ENEOSホールディングス|石油・エネルギー|ENEOS、石油精製、素材|原油価格、脱炭素|石油マージンと資源価格
1605.T|INPEX|石油・天然ガス|原油・天然ガス開発|資源価格、地政学|原油・天然ガス市況
8058.T|三菱商事|総合商社|資源、食品、産業インフラ|資源価格、為替|資源・非資源投資
8001.T|伊藤忠商事|総合商社|ファミリーマート、繊維、食品|消費、為替|非資源事業と小売需要
8031.T|三井物産|総合商社|エネルギー、金属、食品|資源価格、為替|資源とインフラ投資
4502.T|武田薬品工業|製薬|エンティビオ、タケキャブ|特許切れ、負債|新薬販売と研究開発
4503.T|アステラス製薬|製薬|イクスタンジ、パドセブ|特許切れ、研究開発|新薬パイプライン
4523.T|エーザイ|製薬|レケンビ、レンビマ|臨床試験、薬価|アルツハイマー病治療薬の普及
4568.T|第一三共|製薬|エンハーツ、ダトロウェイ|臨床試験、薬価|ADC抗がん剤の成長
4519.T|中外製薬|製薬|ヘムライブラ、アクテムラ|新薬開発、薬価|抗体医薬品需要
6869.T|シスメックス|医療検査機器|XNシリーズ、検査試薬|中国需要、競争|検査装置と試薬販売
7733.T|オリンパス|医療機器|EVIS X1、内視鏡|品質管理、規制|医療用内視鏡需要
4543.T|テルモ|医療機器|カテーテル、血液管理機器|品質管理、規制|医療機器と海外需要
4452.T|花王|日用品・化学|アタック、ビオレ、キュレル|原材料、中国需要|日用品と化粧品需要
4911.T|資生堂|化粧品|SHISEIDO、クレ・ド・ポー ボーテ|中国需要、利益率|高級化粧品需要
4922.T|コーセーホールディングス|化粧品|DECORTÉ、雪肌精、ADDICTION|中国需要、利益率|高級化粧品と免税需要
8113.T|ユニ・チャーム|衛生用品|ムーニー、ソフィ、ライフリー|出生率、原材料|衛生用品とアジア需要
2267.T|ヤクルト本社|食品・乳酸菌飲料|ヤクルト、Yakult1000、ジョア|中国需要、原材料|乳酸菌飲料と海外販売
2801.T|キッコーマン|食品・調味料|キッコーマンしょうゆ、デルモンテ|為替、原材料|海外しょうゆ販売
2802.T|味の素|食品・電子材料|味の素、ほんだし、ABF|原材料、為替|食品と半導体材料需要
2502.T|アサヒグループホールディングス|飲料・食品|アサヒスーパードライ、カルピス|原材料、消費|国内外の飲料需要
2503.T|キリンホールディングス|飲料・医薬|キリン一番搾り、午後の紅茶|原材料、消費|飲料とヘルスサイエンス
2914.T|日本たばこ産業|たばこ・食品|MEVIUS、Winston|規制、為替|海外たばこ事業
1928.T|積水ハウス|住宅建設|積水ハウス、シャーメゾン|住宅金利、資材費|国内外住宅需要
1802.T|大林組|ゼネコン|建築、土木、都市開発|人件費、資材費|国内インフラ投資
1812.T|鹿島建設|ゼネコン|建築、土木、不動産開発|資材費、人件費|都市再開発と公共投資
9201.T|日本航空|航空|JAL、ZIPAIR|燃料費、為替|旅客需要と訪日観光
9202.T|ANAホールディングス|航空|ANA、Peach|燃料費、為替|旅客需要と国際線
4689.T|LINEヤフー|インターネットサービス|LINE、Yahoo! JAPAN、PayPay関連|広告市況、競争|広告とEC需要
4755.T|楽天グループ|EC・金融・通信|楽天市場、楽天カード、楽天モバイル|負債、通信投資|モバイル事業の収益改善
2413.T|エムスリー|医療IT|m3.com、医師向け情報サービス|医薬品広告、競争|医療DXと医師向けサービス
3064.T|MonotaRO|工場向けEC|モノタロウ、工場用品通販|物流費、競争|企業の間接材調達
'''
US = '''
AAPL|Apple|スマートフォン・PCメーカー|iPhone、Mac、App Store|中国需要、規制|端末買い替えとサービス収益
MSFT|Microsoft|クラウド・ソフトウェア|Azure、Microsoft 365、Copilot|AI投資、競争|クラウドと生成AI需要
NVDA|NVIDIA|半導体設計|GPU、CUDA、DGX|輸出規制、競争|AI計算需要とデータセンター投資
GOOGL|Alphabet|検索・広告・クラウド|Google検索、YouTube、Google Cloud|規制、AI競争|検索広告とクラウド需要
AMZN|Amazon|EC・クラウド|Amazon、AWS、Prime|設備投資、競争|クラウドとEC需要
META|Meta Platforms|SNS・広告|Facebook、Instagram、WhatsApp|規制、AI投資|広告市場とAI機能
TSLA|Tesla|電気自動車・エネルギー|Model 3、Model Y、Powerwall|EV競争、利益率|EV需要と自動運転開発
AVGO|Broadcom|半導体・インフラソフト|ネットワーク半導体、VMware|顧客集中、負債|AIネットワーク需要
AMD|Advanced Micro Devices|半導体|Ryzen、EPYC、Instinct|競争、半導体市況|AI GPUとサーバー需要
INTC|Intel|半導体メーカー|Core、Xeon、Intel Foundry|設備投資、競争|半導体製造再建
MU|Micron Technology|メモリ半導体|DRAM、HBM、NAND|メモリ市況、設備投資|AI向けメモリ需要
QCOM|Qualcomm|通信半導体|Snapdragon、モデム|スマホ需要、特許|スマホとエッジAI
ARM|Arm Holdings|半導体IP|Arm CPU IP、Neoverse|ライセンス、競争|サーバーとスマホの設計需要
TXN|Texas Instruments|アナログ半導体|アナログIC、組込みプロセッサ|産業需要、設備投資|産業機器と車載半導体
ADI|Analog Devices|アナログ半導体|データコンバータ、電源管理|産業需要、競争|工場・車載の電子化
AMAT|Applied Materials|半導体製造装置|成膜装置、検査装置|輸出規制、設備投資|半導体設備投資
LRCX|Lam Research|半導体製造装置|エッチング装置、成膜装置|輸出規制、設備投資|半導体製造能力増強
KLAC|KLA|半導体検査装置|検査装置、計測装置|設備投資、顧客集中|半導体歩留まり改善
ASML|ASML Holding|露光装置|EUV、DUV露光装置|輸出規制、顧客集中|先端半導体投資
ORCL|Oracle|企業向けソフト・クラウド|Oracle Database、OCI、NetSuite|設備投資、負債|AIクラウドとデータベース
CRM|Salesforce|企業向けCRM|Sales Cloud、Service Cloud、Slack|競争、成長鈍化|企業のCRM投資
ADBE|Adobe|クリエイティブソフト|Photoshop、Acrobat、Firefly|生成AI競争、解約|デザインソフトとAI需要
NOW|ServiceNow|企業向け業務ソフト|Now Platform、ITSM|高い評価額、競争|企業の業務自動化
SNOW|Snowflake|クラウドデータ基盤|Snowflake Data Cloud|競争、クラウド費用|データ分析とAI活用
PLTR|Palantir Technologies|データ分析ソフト|Gotham、Foundry、AIP|評価額、政府案件|政府・企業AI導入
IBM|IBM|企業向けIT|watsonx、Red Hat、メインフレーム|成長鈍化、競争|企業AIとハイブリッドクラウド
CSCO|Cisco Systems|ネットワーク機器|Catalyst、Webex、Splunk|IT投資、競争|企業ネットワークとセキュリティ
PANW|Palo Alto Networks|サイバーセキュリティ|Prisma、Cortex、NGFW|競争、買収統合|クラウドセキュリティ需要
CRWD|CrowdStrike|サイバーセキュリティ|Falcon|競争、障害対応|エンドポイント防御需要
FTNT|Fortinet|サイバーセキュリティ|FortiGate、Fortinet Security Fabric|競争、IT投資|ネットワーク防御需要
ZS|Zscaler|クラウドセキュリティ|ZIA、ZPA|競争、成長鈍化|ゼロトラスト導入
NET|Cloudflare|ネットワーク・セキュリティ|Workers、R2、WAF|競争、利益率|エッジ計算とセキュリティ
SHOP|Shopify|ECプラットフォーム|Shopify、Shop Pay|消費、競争|中小企業のEC需要
PYPL|PayPal|オンライン決済|PayPal、Venmo、Braintree|競争、手数料|デジタル決済需要
V|Visa|決済ネットワーク|Visaカード、Visa Direct|規制、手数料|キャッシュレス決済
MA|Mastercard|決済ネットワーク|Mastercard、Mastercard Send|規制、手数料|電子決済と海外旅行
AXP|American Express|カード・金融|American Express、Membership Rewards|信用費用、消費|高所得層のカード決済
JPM|JPMorgan Chase|銀行・金融|Chase、J.P. Morgan|信用費用、金利|融資と投資銀行業務
BAC|Bank of America|銀行・金融|Bank of America、Merrill|信用費用、金利|金利と融資需要
WFC|Wells Fargo|銀行・金融|Wells Fargo、住宅ローン|規制、信用費用|融資と手数料収益
GS|Goldman Sachs|投資銀行|Goldman Sachs、資産運用|市場変動、規制|M&Aと資本市場
MS|Morgan Stanley|証券・資産運用|Morgan Stanley、E*TRADE|市場変動、規制|資産運用と投資銀行
BLK|BlackRock|資産運用|iShares、Aladdin|市場変動、手数料|ETFと運用資産
UNH|UnitedHealth Group|医療保険・医療サービス|UnitedHealthcare、Optum|医療費、規制|医療保険と医療サービス
HUM|Humana|医療保険|Medicare Advantage、CenterWell|医療費、制度変更|高齢者向け医療保険
PFE|Pfizer|製薬|Prevnar、Eliquis、Comirnaty|特許切れ、研究開発|新薬と抗がん剤需要
MRK|Merck & Co.|製薬|Keytruda、Gardasil|特許切れ、研究開発|抗がん剤とワクチン
LLY|Eli Lilly|製薬|Mounjaro、Zepbound|薬価、競争|肥満症と糖尿病治療薬
NVO|Novo Nordisk|製薬|Ozempic、Wegovy、Rybelsus|競争、薬価|肥満症治療薬市場
ABBV|AbbVie|製薬|Skyrizi、Rinvoq|特許切れ、研究開発|免疫疾患治療薬
AMGN|Amgen|バイオ医薬品|Repatha、Prolia|特許、研究開発|バイオ医薬品需要
GILD|Gilead Sciences|製薬|Biktarvy、Trodelvy|特許、研究開発|HIVと抗がん剤
REGN|Regeneron Pharmaceuticals|バイオ医薬品|Eylea、Dupixent|競争、研究開発|眼科・免疫疾患治療薬
VRTX|Vertex Pharmaceuticals|バイオ医薬品|Trikafta、Casgevy|研究開発、製品集中|希少疾患治療薬
ISRG|Intuitive Surgical|手術支援ロボット|da Vinci、Ion|設備投資、競争|ロボット手術の普及
TMO|Thermo Fisher Scientific|科学機器|質量分析装置、検査試薬|研究投資、競争|製薬研究と検査需要
DHR|Danaher|ライフサイエンス機器|Cytiva、Beckman Coulter|研究投資、競争|医薬品製造・研究需要
CAT|Caterpillar|建設・鉱山機械|CAT、建設機械、発電設備|景気、資源価格|インフラ・鉱山投資
DE|Deere & Company|農業機械|John Deere、農業トラクター|農業市況、関税|農業設備投資
GE|GE Aerospace|航空エンジン|LEAP、航空機エンジン|品質、航空需要|航空機製造と整備需要
BA|Boeing|航空機・防衛|737、787、航空宇宙|品質、負債|航空機納入と防衛需要
LMT|Lockheed Martin|防衛・航空宇宙|F-35、ミサイル防衛|政府予算、案件|防衛予算と航空宇宙需要
RTX|RTX Corporation|航空宇宙・防衛|Pratt & Whitney、Raytheon|品質、政府予算|航空エンジンと防衛需要
HON|Honeywell|産業機器|航空宇宙、ビル制御|設備投資、競争|産業自動化と航空需要
UPS|United Parcel Service|物流・宅配|UPS Ground、UPS Air|燃料費、人件費|物流需要と配送単価
FDX|FedEx|物流・宅配|FedEx Express、FedEx Ground|燃料費、景気|国際物流とEC配送
DAL|Delta Air Lines|航空|Delta、SkyMiles|燃料費、景気|旅客需要と航空運賃
UAL|United Airlines|航空|United、MileagePlus|燃料費、景気|国際線需要
XOM|Exxon Mobil|石油・ガス|Exxon、Mobil|原油価格、規制|原油・天然ガス市況
CVX|Chevron|石油・ガス|Chevron、Texaco|原油価格、規制|原油・天然ガス市況
COP|ConocoPhillips|石油・ガス開発|石油・ガス探鉱開発|原油価格、地政学|原油価格と生産量
NEE|NextEra Energy|電力・再生可能エネルギー|Florida Power & Light、NextEra Energy Resources|金利、設備投資|電力需要と再生可能エネルギー
DUK|Duke Energy|電力会社|Duke Energy、電力供給|規制、設備投資|電力需要と料金規制
CEG|Constellation Energy|発電・電力|原子力発電、電力販売|規制、設備投資|データセンター電力需要
KO|Coca-Cola|飲料|Coca-Cola、Sprite、Fanta|原材料、為替|世界の清涼飲料需要
PEP|PepsiCo|飲料・食品|Pepsi、Lay's、Gatorade|原材料、消費|飲料とスナック需要
PG|Procter & Gamble|日用品|Pampers、Tide、Gillette|原材料、競争|日用品と価格転嫁
CL|Colgate-Palmolive|日用品|Colgate、Palmolive、Hill's|原材料、為替|歯磨きとペットフード
KHC|Kraft Heinz|加工食品|Heinz、Kraft、Philadelphia|売上減、減損|加工食品とブランド再建
HRL|Hormel Foods|加工食品|SPAM、SKIPPY、Planters|原材料、利益率|加工食品需要
GIS|General Mills|加工食品|Cheerios、Häagen-Dazs|原材料、消費|食品需要と価格転嫁
CPB|The Campbell's Company|加工食品|Campbell's、Goldfish|原材料、競争|加工食品とスナック需要
WMT|Walmart|小売|Walmart、Sam's Club|人件費、消費|食品小売とEC
COST|Costco Wholesale|会員制小売|Costco、Kirkland Signature|会員数、評価額|会員制小売と消費
TGT|Target|総合小売|Target、Good & Gather|消費低迷、在庫|米国消費と店舗収益
HD|Home Depot|住宅用品小売|Home Depot、Husky|住宅市況、金利|住宅リフォーム需要
LOW|Lowe's|住宅用品小売|Lowe's、Kobalt|住宅市況、金利|住宅リフォーム需要
NKE|Nike|スポーツ用品|Nike、Jordan、Converse|競争、中国需要|ブランド再建とスポーツ需要
LULU|Lululemon Athletica|スポーツ衣料|lululemon、Align|競争、消費|スポーツ衣料と海外展開
SBUX|Starbucks|コーヒーチェーン|Starbucks、Reserve|人件費、中国需要|既存店売上と店舗再建
MCD|McDonald's|外食チェーン|McDonald's、McCafé|人件費、消費|外食需要と加盟店
CMG|Chipotle Mexican Grill|外食チェーン|Chipotle、ブリトー、ボウル|食材費、人件費|外食需要と既存店売上
DIS|Walt Disney|エンタメ・テーマパーク|Disney、Marvel、Pixar、Disney+|制作費、競争|テーマパークと動画配信
NFLX|Netflix|動画配信|Netflix、Netflix Originals|制作費、競争|有料会員と広告配信
CMCSA|Comcast|通信・メディア|Xfinity、NBC、Universal|通信競争、負債|ブロードバンドと動画配信
VZ|Verizon Communications|通信|Verizon Wireless、Fios|競争、設備投資|5G通信と契約者数
T|AT&T|通信|AT&T、5G、光ファイバー|競争、負債|通信料金と光回線
TMUS|T-Mobile US|通信|T-Mobile、5G Home Internet|競争、設備投資|携帯通信と家庭向けネット
AMT|American Tower|通信塔REIT|通信塔リース|金利、負債|通信設備投資
CCI|Crown Castle|通信塔REIT|通信塔リース|金利、負債|通信設備投資
VRSK|Verisk Analytics|保険データ分析|保険リスク分析、請求分析|競争、規制|保険会社のデータ需要
EL|Estée Lauder|化粧品|Estée Lauder、Clinique、La Mer|中国需要、利益率|高級化粧品市場
FIS|Fidelity National Information Services|金融IT|決済システム、銀行IT|競争、システム|銀行のデジタル化
'''


def parse(block, market):
    out = []
    for line in block.strip().splitlines():
        cells = [c.strip() for c in line.split('|')]
        if len(cells) != 6:
            raise ValueError(line)
        out.append(dict(zip(('ticker','name','business','brands','risks','environment'),cells),market=market))
    return out

if __name__ == '__main__':
    entries = parse(JP,'JP')+parse(US,'US')
    dest = Path(__file__).resolve().parents[1]/'config/universe.json'
    dest.write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Wrote {len(entries)} curated stocks: JP {len(parse(JP,"JP"))}, US {len(parse(US,"US"))}')