# バックテスト実験管理・可視化アプリ

## 名前の定義

- exp_name : ノートブック単位の実験の名前
- run_name : 単一ノートブック内(複数実験想定)での各実験の名前

## 1. 保存データ仕様

### 1.1. 収益 (PnL) + 予測値関連(Prediction / Position)

- (optional)銘柄毎の時系列データフレーム

カラム：pnl + pred + position + その他条件カラム

pnl : 任意

pred : 任意

position : 任意

※ただしpnl/pred/positionの内最低１つはカラムに存在すること

必須その他条件カラム：split(train/val/test) 、epoch、ticker

任意その他条件カラム例：random seed等

index :：datetime index, その他条件カラムでgroupbyして一意制約

保存パス：{base_dir}/{exp_name}/{run_name}/pnl_pred_position/ticker/data.parquet

- (optional)任意個別条件毎の時系列データフレーム

複数弱学習モデル作るケースなど任意の個別条件に対応

カラム：pnl + pred + position + その他条件カラム

pnl : 任意

pred : 任意

position : 任意

※ただしpnl/pred/positionの内最低１つはカラムに存在すること

必須その他条件カラム：split(train/val/test) 、epoch

任意その他条件カラム例：model id、random seed等なんでも

index :：datetime index, その他条件カラムでgroupbyして一意制約

保存パス：{base_dir}/{exp_name}/{run_name}/pnl_pred_position/individual/data.parquet

- 戦略(longshort分位ポートフォリオ/シードアンサンブル等)毎の時系列データフレーム

上記の銘柄/個別条件毎等を組み合わせた最終的な収益となる各戦略用

カラム：pnl + pred + position + その他条件カラム

pnl : 必須

pred : 任意

position : 任意

必須その他条件カラム：split(train/val/test) 、epoch、strategy_name

任意その他条件カラム例：

index :：datetime index, その他条件カラムでgroupbyして一意制約

保存パス：{base_dir}/{exp_name}/{run_name}/pnl_pred_position/strategy/data.parquet

※pnl  / pred / position以外のカラムは自動的にその他条件カラムとして扱う

### 1.2. メトリクス統計値

- 戦略毎統計メトリック(Annual Return/Risk/Sharpe等)のエポック推移データフレーム

カラム：各メトリック名 + その他条件カラム

各メトリック名：実験毎で任意

必須その他条件カラム：split(train/val/test) 、epoch、strategy_name

任意その他条件カラム例：

index：無し(なんでも)

保存パス：{base_dir}/{exp_name}/{run_name}/stats_metrics/strategy/data.parquet

- (optional)任意個別条件毎の統計メトリック(Annual Return/Risk/Sharpe等)のエポック推移データフレーム

カラム：各メトリック名 + その他条件カラム

各メトリック名：実験毎で任意

必須その他条件カラム：split(train/val/test) 、epoch

任意その他条件カラム例：model id、random seed等なんでも

index：無し(なんでも)

保存パス：{base_dir}/{exp_name}/{run_name}/stats_metrics/indivisual/data.parquet

※ 各メトリック名は実験毎に変わるのでなので、条件カラムnon_metric_columns指定させ、all_columns-non_metric_columnsをメトリクスカラムとして処理する

### 1.3. (optional)コード

- 実験コード

保存パス：{base_dir}/{exp_name}/{run_name}/codes/{XXX}.txt

### 1.4. (optional)条件ハイパーパラメータ

- 前処理 / 特徴量 / モデル / 学習 / 評価等すべての条件ハイパーパラメータ

保存パス：{base_dir}/{exp_name}/{run_name}/params/{XXX}.yaml

## 2. 保存機能仕様

1で定義したデータをそれぞれ受け取って仕様のファイルパスに保存する。

主にjupyter上でバックテスト実験を行い、jupyterから本アプリ保存機能API経由で保存を行う想定。

- dfデータを受け取り上記仕様で必須カラムのvalidationを行う
- 時系列のデータ(pnl_pred_position)は、その他条件でgroupbyしてindexが一意になることをvalidation行う
- ハイパーパラメータはdictで受け取ってyamlに変換して保存する
- 統計メトリクスデータに関しては同出力ディレクトリ内にmeta.yamlを作成しnon_metric_columnsを保存しappで可視化する際に読み込んで活用できるよう

## 3. 可視化機能

- streamlit用いてwebダッシュボードアプリとして実装
- 上記データ仕様に従ってデータが保存されている前提でそれを適宜読み込み表示する
- 欲しい機能
    - exp x run単位の詳細ダッシュボード
        - exp x run一覧から選択できるようにし、選択されたら以下の詳細を表示する
        - 統計値メトリクスを表で表示（split毎に分ける）
        - 各統計メトリクスのエポック推移グラフ（split毎に分ける）
            - best epochも算出する。bestの判断にどのメトリクスを使用させるかはメトリクスカラムリストからユーザーに選択させる(基本デフォルトsharpe系で)
        - (エポック指定可で)戦略毎の累積(cumsum)PnLの時系列(資産曲線)
            - ↑ではbest epochがどのエポックかわかるようにし、デフォルトではbest epochが選択された状態にする。
            - split毎に(色など)分ける。(基本期間はかぶらない想定なので1グラフでいい想定)
        - 戦略毎のポジションの時系列
            - 資産曲線の表示で選択されてるエポックのポジションを表示する
            - split毎に(色など)分ける。(基本期間はかぶらない想定なので1グラフでいい想定)

## 4. 表示仕様

### 4.1. メトリクス - グラフの表示

- ベストエポック判定に使うsplit x 各メトリックカラム名 x strategy_nameはユーザーに選択させる(デフォルトはsplit=test & メトリック名=sharpe含む & strategy_name)
- split毎にグラフを分けて*横に並べて*表示する。チェックボックスで表示するsplitを選択できるようにする。デフォルトすべて表示(選択)。
- 各strategy_nameは*同一*グラフ内に表示する。ベンチマークのstrategy_name(buy&hold)はstrategy_nameから選択できるようにし(選択無し可のプルダウン/チェックボックスなど)、ベンチマークと選択された系列は赤色で強調して表示する。
- 各メトリック毎にグラフを分けて*縦*に並べて*表示する

### 4.2. メトリクス - 表の表示

- 表示するのは**meanやらstdやら統計値とったデータではなく**て、生データを下記記載の方法で分割/整形した上で表で表示する。indexはエポックとなるようにする(重複ないように)。
- グラフ同様splitは横に分けて別表として表示。チェックボックスで表示するsplitを選択できるようにする。デフォルトすべて表示(選択)。
- strategy_nameはunstackする感じで、カラム名を{メトリクス名}_{strategy_name}として横持にして表示する
