# 金（XAUUSD）の日中の値動きに関する既存研究のまとめ

ルール探索（`python -m xauforecast rules`）で優先的に検証すべき仮説を、公開されている研究・資料から整理したものです。
多くは特定の期間・市場での結果で、査読のない修士論文や実務家の資料も含みます。**そのまま使える優位性ではなく、
自分のデータで検証する仮説**として扱ってください（2026 年 11 月時点のウェブ検索に基づく）。

## 1. ロンドン・フィキシング前後の下落

| 資料 | 内容 | 本ツールでの検証 |
|---|---|---|
| Caminschi & Heaney (2014), *Journal of Futures Markets* 34(11) "Fixing a Leaky Fixing" | PM フィキシング開始後の 4 分間に、金先物（GC）と GLD で情報を持つ参加者に有利な異常リターン。結果公表後には有意な反応なし（「情報が漏れていた」） | K 群: PM フィックスの前後 5〜30 分の売り / 買い |
| チューリッヒ大学の修士論文 "Intraday Price Anomalies in the Gold and Silver Market" | 金の平均リターンは AM / PM フィックス前後が 1 日で最もマイナス。最良の戦略は「ロンドン始値から PM フィックスまで売り、残りは買い」 | K 群: 「ロンドン始値→PM フィックス 売り」「PM フィックス→NY17 時 買い」 |
| コペンハーゲン・ビジネススクールの学生論文 "Gold Price Dynamics Around the Clock" | 東洋（アジア）の取引時間に上昇し、それ以外の時間に下落する山型の日中パターン。操作が疑われた期間はフィキシング前後に下落 | K 群: 「アジア開始→ロンドン 8:00 買い」、C 群の時間帯保有 |
| NYU の銀に関するワーキングペーパー | 銀のフィキシング前後に約 12bp の下方バイアス | （銀は対象外） |
| LBMA Alchemist（Peter Fertig）など反論 | 操作の証拠とは言えず、他の要因で説明できるという反論 | — |

**注意**: これらの多くは 2000〜2014 年頃のデータです。2015 年にフィキシングは電子オークション（LBMA Gold Price）に
移行しており、効果が消えている可能性があります。年ごとに分けて確認することが重要です。

## 2. FOMC・雇用統計への反応

| 資料 | 内容 | 本ツールでの検証 |
|---|---|---|
| Awartani, Hussain & Virk (2024), *International Review of Financial Analysis* | FOMC の金利サプライズに対し、金のリターンとボラは引き締め方向より緩和方向のサプライズに強く反応。価格の調整は 5 分を超えて続く（短期的な非効率の可能性） | L 群: FOMC 発表の初動 1/5/15 分に順張り、15 分〜引けまで保有 |
| FXStreet の雇用統計イベントスタディ（約 20 回分、実務家の資料） | 予想を下回ると 15 分後に平均 +$4〜6、上回ると −$4.8。4 時間後には関係が弱まる | B 群: 8:30（雇用統計日のみ）の初動に順張り、保有 15〜240 分 |

## 3. 日中モメンタム（最初の 30 分が最後の 30 分を予測）

| 資料 | 内容 | 本ツールでの検証 |
|---|---|---|
| Gao, Han, Li & Zhou "Market Intraday Momentum"（S&P500 ETF、1993〜2013） | 最初の 30 分のリターンが最後の 30 分を予測。ボラ・出来高が高い日に強い | J 群: 「前日終値→8:50 の方向で 16:30〜17:00」 |
| 中国の金属先物の研究 | 夜間取引の導入後は、夜間の最初の 30 分が予測力を持つ | J 群: 「アジア（18-3 時）の方向」系 |
| アジア太平洋の ETF の研究 | 香港・シンガポールでは全期間では観測されず | — |

金先物そのものでの確立した証拠は見つかりませんでした。

## 4. 曜日・月・月末月初

| 資料 | 内容 |
|---|---|
| 台湾の修士論文（商品先物 1983〜2011） | 金先物で季節性（曜日・月末月初・1 月効果）が他の先物より頻繁に見られる |
| ボルサ・イスタンブールの金先物（2013〜2022） | 木曜以外はプラス、1 月と 3 月にプラス |
| Borowski & Łukasik（2019、金属市場） | 金の月効果はなし、週末効果はあり |

結果は研究によってまちまちです。統計レポート（`stats.md` の曜日別・月別・月末月初）で確認できます。

## 5. ロンドン時間のレンジブレイク

公開されているバックテストのほとんどは、EA（自動売買プログラム）の販売者や個人ブログによるもので、独立した検証は
見つかりませんでした。ある実務家は「固定スプレッドのバックテストでシャープレシオ 2.5 でも、優位性が寄り付き数分の
スプレッドが広い時間に集中していると、実運用では損益ゼロ近くになる」と指摘しています。本ツールではこれを受けて、
**スプレッドを時間帯で変えて**（再開直後 4 倍、指標直後 3 倍など）コストを計算しています。

## 出典

- [Caminschi & Heaney (2014) "Fixing a Leaky Fixing" (IDEAS/RePEc)](https://ideas.repec.org/a/wly/jfutmk/v34y2014i11p1003-1039.html)
- [Caminschi & Heaney 作業論文 (UWA)](https://api.research-repository.uwa.edu.au/ws/files/4725264/A0205_use_this.pdf)
- [Intraday Price Anomalies in the Gold and Silver Market（チューリッヒ大学）](https://www.merlin.uzh.ch/publication/show/11299)
- [Gold Price Dynamics Around the Clock（コペンハーゲン・ビジネススクール）](https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/)
- [Any Silver Linings（NYU Stern 作業論文）](https://www.stern.nyu.edu/sites/default/files/assets/documents/Any%20Silver%20Linings%20-%20WORKING%20PAPER%20-%2020140707%20-%20Merged.pdf)
- [LBMA Alchemist: Has there been a decade of London PM gold fixing manipulation?](https://www.lbma.org.uk/alchemist/issue-73/has-there-been-a-decade-of-london-pm-gold-fixing-manipulation)
- [How do the gold intra-day returns and volatility react to monetary policy shocks?（Awartani ほか）](https://pure.kfupm.edu.sa/en/publications/how-do-the-gold-intra-day-returns-and-volatility-react-to-monetar/)
- [FXStreet: 雇用統計への金の反応の分析（2024 年 10 月）](https://www.fxstreet.com/analysis/us-october-nonfarm-payrolls-preview-analyzing-gold-price-reaction-to-nfp-surprises-202410311000)
- [FXStreet: 雇用統計への金の反応の分析（2023 年 11 月）](https://www.fxstreet.com/analysis/us-november-nonfarm-payrolls-preview-analyzing-gold-prices-reaction-to-nfp-surprises-202312071132)
- [Gao, Han, Li & Zhou "Market Intraday Momentum"](https://www3.nd.edu/~zda/intramom.pdf)
- [Alpha Architect: The first half-hour return predicts the last half-hour return](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/)
- [中国の金属先物の日中モメンタム（AUT）](https://acfr.aut.ac.nz/__data/assets/pdf_file/0008/686816/4a-Z-Ivy-Zhou.pdf)
- [Borowski & Łukasik: Analysis of Selected Seasonality Effects in the Metal Markets](https://econjournals.sgh.waw.pl/JMFS/article/view/740)
- [ボルサ・イスタンブール金先物の季節性](https://acikerisim.siirt.edu.tr/items/4493f29e-de1c-40df-b8a6-bb19293df4eb)
- [台湾の修士論文（商品先物の季節性）](https://ndltd.ncl.edu.tw/r/33806193183408837039)
- [London Breakout on Gold: 3.7 Years of Backtests（MQL5 ブログ）](https://www.mql5.com/en/blogs/post/777540)
- [FOMC 2025〜2026 年の日程（ABA Banking Journal）](https://bankingjournal.aba.com/2024/08/fomc-releases-tentative-meeting-schedule-for-2025-2026)
- [FOMC 公式カレンダー（Federal Reserve）](https://federalreserve.gov/monetarypolicy/fomccalendars.htm)
